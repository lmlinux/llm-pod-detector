from kubernetes import client
from kubernetes.client import ApiClient, Configuration
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

def create_k8s_client(api_url: str, token: str) -> ApiClient:
    """创建Kubernetes API客户端"""
    config = Configuration()
    config.host = api_url
    config.api_key_prefix['authorization'] = 'Bearer'
    config.api_key['authorization'] = token
    config.verify_ssl = False
    return ApiClient(config)

def get_non_running_pods(api_client: ApiClient) -> List[Dict]:
    """获取非Running状态的Pods"""
    core_api = client.CoreV1Api(api_client)
    namespaces = core_api.list_namespace().items
    results = []
    
    for ns in namespaces:
        pods = core_api.list_namespaced_pod(ns.metadata.name)
        for pod in pods.items:
            if pod.status.phase not in ("Running", "Succeeded"):
                results.append({
                    "namespace": pod.metadata.namespace,
                    "pod_name": pod.metadata.name,
                    "status": pod.status.phase
                })
    return results

def get_pod_diagnostic_data(api_client: ApiClient, namespace: str, pod_name: str) -> Dict:
    """获取完整的诊断数据"""
    core_api = client.CoreV1Api(api_client)
    data = {"basic": {}, "events": [], "logs": {}}
    
    try:
        # 获取Pod基本信息
        pod = core_api.read_namespaced_pod(pod_name, namespace)
        
        # 检查 container_statuses 是否为 None
        container_statuses = pod.status.container_statuses if pod.status.container_statuses else []
        
        data["basic"] = {
            "name": pod.metadata.name,
            "namespace": namespace,
            "status": pod.status.phase,
            "restart_count": sum(c.restart_count for c in container_statuses),  # 安全计算重启次数
            "node": pod.spec.node_name
        }
        
        # 获取事件
        events = core_api.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={pod_name}"
        )
        data["events"] = [{
            "type": e.type,
            "reason": e.reason,
            "message": e.message,
            "last_time": e.last_timestamp
        } for e in events.items[:5]]  # 取最近5个事件
        
        # 获取日志
        data["logs"] = {}
        for container in pod.spec.containers:
            try:
                current_logs = core_api.read_namespaced_pod_log(
                    pod_name, namespace, container=container.name, tail_lines=100
                )
                previous_logs = core_api.read_namespaced_pod_log(
                    pod_name, namespace, container=container.name, previous=True, tail_lines=100
                ) if data["basic"]["restart_count"] > 0 else ""
                data["logs"][container.name] = {
                    "current": current_logs,
                    "previous": previous_logs
                }
            except client.ApiException as e:
                data["logs"][container.name] = {"error": str(e)}
                
    except client.ApiException as e:
        data["error"] = str(e)
        
    return data


def get_namespaces(api_client: ApiClient) -> List[str]:
    """获取所有命名空间"""
    core_api = client.CoreV1Api(api_client)
    namespaces = core_api.list_namespace().items
    return [ns.metadata.name for ns in namespaces]

def get_applications(api_client: ApiClient, namespace: str) -> List[str]:
    """获取指定命名空间下的部署应用列表"""
    apps_api = client.AppsV1Api(api_client)
    try:
        deployments = apps_api.list_namespaced_deployment(namespace).items
        return [d.metadata.name for d in deployments]
    except client.ApiException:
        return []

def get_application_status(api_client: ApiClient, namespace: str, app_name: str) -> Dict:
    """获取应用详细状态"""
    apps_api = client.AppsV1Api(api_client)
    try:
        deployment = apps_api.read_namespaced_deployment(app_name, namespace)
        return {
            "deployment_status": deployment.status.conditions[-1].type if deployment.status.conditions else "Unknown",
            "replicas": deployment.spec.replicas,
            "available_replicas": deployment.status.available_replicas,
            "unavailable_replicas": deployment.status.unavailable_replicas,
            "updated_replicas": deployment.status.updated_replicas,
            "last_update": str(deployment.metadata.creation_timestamp),
            "containers": [c.name for c in deployment.spec.template.spec.containers]
        }
    except client.ApiException as e:
        return {"error": f"获取应用状态失败: {str(e)}"}
    
def get_all_applications(api_client: ApiClient) -> List[Dict]:
    """获取全集群所有命名空间的部署应用"""
    apps_api = client.AppsV1Api(api_client)
    core_api = client.CoreV1Api(api_client)
    results = []
    
    try:
        # 获取所有命名空间
        namespaces = [ns.metadata.name for ns in core_api.list_namespace().items]
        
        # 并行获取各命名空间部署
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for ns in namespaces:
                futures.append(executor.submit(
                    apps_api.list_namespaced_deployment,
                    namespace=ns
                ))
            
            for future in as_completed(futures):
                try:
                    deployments = future.result().items
                    for d in deployments:
                        results.append({
                            "name": d.metadata.name,
                            "namespace": d.metadata.namespace,
                            "creation_time": str(d.metadata.creation_timestamp)
                        })
                except client.ApiException:
                    continue
    except Exception as e:
        print(f"Error fetching cluster apps: {str(e)}")
    
    # 按创建时间排序（新应用在前）
    return sorted(results, key=lambda x: x["creation_time"], reverse=True)

def get_application_pods(api_client: ApiClient, namespace: str, app_name: str) -> List[Dict]:
    """获取指定应用的所有Pod信息"""
    core_api = client.CoreV1Api(api_client)
    apps_api = client.AppsV1Api(api_client)
    
    try:
        # 获取Deployment的标签选择器
        deployment = apps_api.read_namespaced_deployment(app_name, namespace)
        label_selector = deployment.spec.selector.match_labels
        
        # 构建标签选择器查询字符串
        selector_str = ",".join([f"{k}={v}" for k,v in label_selector.items()])
        
        # 获取匹配的Pod
        pods = core_api.list_namespaced_pod(
            namespace=namespace,
            label_selector=selector_str
        ).items
        
        results = []
        for pod in pods:
            container_statuses = pod.status.container_statuses or []
            restart_count = sum(c.restart_count for c in container_statuses)
            
            results.append({
                "namespace": pod.metadata.namespace,
                "pod_name": pod.metadata.name,
                "status": pod.status.phase,
                "restart_count": restart_count,
                "node": pod.spec.node_name
            })
            
        return sorted(results, key=lambda x: x["pod_name"])
        
    except client.ApiException as e:
        return [{"error": f"获取Pod失败: {str(e)}"}]
    except Exception as e:
        return [{"error": f"发生未知错误: {str(e)}"}]