# k8s_utils.py
from kubernetes import client
from kubernetes.client import ApiClient, Configuration
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

def create_k8s_client(api_url: str, token: str) -> ApiClient:
    config = Configuration()
    config.host = api_url
    config.api_key_prefix['authorization'] = 'Bearer'
    config.api_key['authorization'] = token
    config.verify_ssl = False
    return ApiClient(config)

def get_non_running_pods(api_client: ApiClient) -> List[Dict]:
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
    core_api = client.CoreV1Api(api_client)
    data = {"basic": {}, "events": [], "logs": {}}
    
    try:
        pod = core_api.read_namespaced_pod(pod_name, namespace)
        
        container_statuses = pod.status.container_statuses if pod.status.container_statuses else []
        
        data["basic"] = {
            "name": pod.metadata.name,
            "namespace": namespace,
            "status": pod.status.phase,
            "restart_count": sum(c.restart_count for c in container_statuses),
            "node": pod.spec.node_name
        }
        
        events = core_api.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={pod_name}"
        )
        data["events"] = [{
            "type": e.type,
            "reason": e.reason,
            "message": e.message,
            "last_time": e.last_timestamp
        } for e in events.items[:5]]
        
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

def get_all_applications(api_client: ApiClient) -> List[Dict]:
    apps_api = client.AppsV1Api(api_client)
    core_api = client.CoreV1Api(api_client)
    results = []
    
    try:
        namespaces = [ns.metadata.name for ns in core_api.list_namespace().items]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for ns in namespaces:
                futures.append(executor.submit(
                    apps_api.list_namespaced_deployment,
                    namespace=ns
                ))
                futures.append(executor.submit(
                    apps_api.list_namespaced_stateful_set,
                    namespace=ns
                ))
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    for item in result.items:
                        kind = "Deployment" if isinstance(item, client.V1Deployment) else "StatefulSet"
                        results.append({
                            "name": item.metadata.name,
                            "namespace": item.metadata.namespace,
                            "kind": kind,
                            "creation_time": str(item.metadata.creation_timestamp)
                        })
                except client.ApiException:
                    continue
    except Exception as e:
        print(f"Error fetching cluster apps: {str(e)}")
    
    return sorted(results, key=lambda x: x["creation_time"], reverse=True)

def get_application_pods(api_client: ApiClient, namespace: str, app_name: str, kind: str) -> List[Dict]:
    core_api = client.CoreV1Api(api_client)
    apps_api = client.AppsV1Api(api_client)
    
    try:
        label_selector = {}
        if kind == "Deployment":
            deployment = apps_api.read_namespaced_deployment(app_name, namespace)
            label_selector = deployment.spec.selector.match_labels
        elif kind == "StatefulSet":
            statefulset = apps_api.read_namespaced_stateful_set(app_name, namespace)
            label_selector = statefulset.spec.selector.match_labels
        
        selector_str = ",".join([f"{k}={v}" for k,v in label_selector.items()])
        
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

def get_cluster_summary(cluster_config: dict) -> dict:
    result = {
        "cluster_name": cluster_config["cluster_name"],
        "status": "error",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nodes": 0,
        "pods": 0,
        "deployments": 0,
        "statefulsets": 0,
        "error": ""
    }
    
    try:
        api_client = create_k8s_client(
            cluster_config["api_url"],
            cluster_config["token"]
        )
        core_api = client.CoreV1Api(api_client)
        apps_api = client.AppsV1Api(api_client)
        
        nodes = core_api.list_node().items
        result["nodes"] = len(nodes)
        
        pods = core_api.list_pod_for_all_namespaces().items
        result["pods"] = len(pods)
        
        deployments = apps_api.list_deployment_for_all_namespaces().items
        result["deployments"] = len(deployments)
        
        statefulsets = apps_api.list_stateful_set_for_all_namespaces().items
        result["statefulsets"] = len(statefulsets)
        
        result["status"] = "success"
        
    except Exception as e:
        result["error"] = f"集群连接异常: {str(e)}"
    
    return result