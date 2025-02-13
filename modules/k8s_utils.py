from kubernetes import client
from kubernetes.client import ApiClient, Configuration
from typing import List, Dict

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
                    pod_name, namespace, container=container.name, tail_lines=50
                )
                previous_logs = core_api.read_namespaced_pod_log(
                    pod_name, namespace, container=container.name, previous=True, tail_lines=50
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