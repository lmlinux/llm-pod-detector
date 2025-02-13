import streamlit as st
from modules.config_loader import load_configs
from modules.k8s_utils import create_k8s_client, get_non_running_pods, get_pod_diagnostic_data
from modules.llm_analyzer import LLMAnalyzer

# 初始化配置
clusters, llm_config = load_configs()
analyzer = LLMAnalyzer(llm_config)

# 页面布局
st.title("K8s 异常Pod诊断")

# 侧边栏
selected_cluster = st.sidebar.radio("选择集群", [c["cluster_name"] for c in clusters])
current_cluster = next(c for c in clusters if c["cluster_name"] == selected_cluster)

# 主界面
with st.spinner(f"正在检查 {selected_cluster} 集群..."):
    api_client = create_k8s_client(current_cluster["api_url"], current_cluster["token"])
    pods = get_non_running_pods(api_client)

if not pods:
    st.success("未发现异常Pod")
    st.stop()

st.subheader("异常Pod列表")
for pod in pods:
    cols = st.columns([3, 2, 2, 3])
    cols[0].write(pod['namespace'])
    cols[1].write(pod["pod_name"])
    cols[2].code(pod["status"])
    
    if cols[3].button("诊断", key=f"btn_{pod['namespace']}_{pod['pod_name']}"):
        with st.spinner("收集诊断信息中..."):
            diagnostic_data = get_pod_diagnostic_data(
                api_client, 
                pod["namespace"], 
                pod["pod_name"]
            )
        
        if "error" in diagnostic_data:
            st.error(diagnostic_data["error"])
        else:
            with st.expander("原始数据"):
                st.json(diagnostic_data)
            
            st.subheader("AI分析结果")
            analysis = analyzer.analyze_pod(diagnostic_data)
            st.markdown(analysis)