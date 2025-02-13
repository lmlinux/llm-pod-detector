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
selected_cluster = st.sidebar.radio("选择集群", ["请选择一个集群"] + [c["cluster_name"] for c in clusters])

# 如果没有选择集群，则不加载任何集群的数据
if selected_cluster == "请选择一个集群":
    st.info("请选择一个集群来查看异常Pod")
    st.stop()

current_cluster = next(c for c in clusters if c["cluster_name"] == selected_cluster)

# 使用会话状态缓存数据
if 'prev_cluster' not in st.session_state or st.session_state.prev_cluster != selected_cluster:
    with st.spinner(f"正在初始化 {selected_cluster} 集群连接..."):
        st.session_state.api_client = create_k8s_client(current_cluster["api_url"], current_cluster["token"])
        st.session_state.prev_cluster = selected_cluster
        st.session_state.pods = get_non_running_pods(st.session_state.api_client)  # 重新获取 pod 列表

# 主界面
with st.spinner(f"正在检查 {selected_cluster} 集群状态..."):
    pods = st.session_state.pods  # 从会话状态获取 pods

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
                st.session_state.api_client,
                pod["namespace"], 
                pod["pod_name"]
            )
        
        if "error" in diagnostic_data:
            st.error(diagnostic_data["error"])
        else:
            with st.expander("原始数据"):
                st.json(diagnostic_data)
            
            # 在进行 AI 分析时，显示等待提示
            with st.spinner("AI 分析中..."):
                analysis = analyzer.analyze_pod(diagnostic_data)
                
            # 使用 expander 折叠 AI 分析结果，默认展开
            with st.expander("AI分析结果", expanded=True):
                st.markdown(analysis)
