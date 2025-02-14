import streamlit as st
from modules.config_loader import load_configs
from modules.k8s_utils import *
from modules.llm_analyzer import LLMAnalyzer

# 初始化配置
clusters, llm_config = load_configs()
analyzer = LLMAnalyzer(llm_config)

# 页面布局
st.title("K8s 集群诊断工具")

# ==========================
# 侧边栏布局
# ==========================
with st.sidebar:
    # 功能选择
    selected_function = st.radio(
        "选择功能",
        ["异常Pod诊断", "应用状态探测"],
        index=0
    )

    # 集群选择
    selected_cluster = st.radio(
        "选择集群",
        ["请选择一个集群"] + [c["cluster_name"] for c in clusters]
    )

# ==========================
# 公共逻辑：集群连接
# ==========================
if selected_cluster != "请选择一个集群":
    current_cluster = next(c for c in clusters if c["cluster_name"] == selected_cluster)
    
    # 维护集群连接状态
    if 'prev_cluster' not in st.session_state or st.session_state.prev_cluster != selected_cluster:
        with st.spinner(f"正在连接集群 {selected_cluster}..."):
            st.session_state.api_client = create_k8s_client(
                current_cluster["api_url"],
                current_cluster["token"]
            )
            st.session_state.prev_cluster = selected_cluster
            
            # 清除旧集群数据缓存（新增应用搜索相关状态清理）
            states_to_clear = [
                'pods', 'all_applications',
                'exploring_app', 'exploring_app_name', 'exploring_namespace',
                'app_search_term', 'selected_app_option'  # 新增两个状态键
            ]
            for state in states_to_clear:
                if state in st.session_state:
                    del st.session_state[state]

# ==========================
# 页面状态清理逻辑
# ==========================
# 如果切换了功能，清理前一个功能的状态
if 'active_function' not in st.session_state:
    st.session_state.active_function = selected_function

if st.session_state.active_function != selected_function:
    st.session_state.active_function = selected_function

    # 清理异常Pod诊断的状态
    if 'pods' in st.session_state:
        del st.session_state.pods
    if 'pods_cluster' in st.session_state:
        del st.session_state.pods_cluster
    if 'pods_error' in st.session_state:
        del st.session_state.pods_error
        
    # 清理应用状态探测的状态
    if 'all_applications' in st.session_state:
        del st.session_state.all_applications
    if 'apps_cluster' in st.session_state:
        del st.session_state.apps_cluster
    if 'apps_error' in st.session_state:
        del st.session_state.apps_error
    if 'exploring_app' in st.session_state:
        del st.session_state.exploring_app
    if 'exploring_app_name' in st.session_state:
        del st.session_state.exploring_app_name
    if 'exploring_namespace' in st.session_state:
        del st.session_state.exploring_namespace

# ==========================
# 功能路由
# ==========================
if selected_function == "异常Pod诊断":
    # ======================
    # 异常Pod诊断功能
    # ======================
    if selected_cluster == "请选择一个集群":
        st.info("请先选择一个集群")
        st.stop()

    # 智能刷新机制
    refresh_flag = False
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button('🔄 刷新列表', help="强制刷新当前集群的Pod状态"):
            refresh_flag = True
            if 'pods' in st.session_state:
                del st.session_state.pods

    # 带状态绑定的数据获取
    if 'pods' not in st.session_state or refresh_flag or \
       st.session_state.get('pods_cluster') != selected_cluster:
        
        with st.spinner("正在获取集群状态..."):
            try:
                st.session_state.pods = get_non_running_pods(st.session_state.api_client)
                st.session_state.pods_cluster = selected_cluster
                st.session_state.pods_error = None
            except Exception as e:
                st.session_state.pods_error = f"集群连接失败: {str(e)}"
                st.session_state.pods = []

    # 错误处理
    if st.session_state.get('pods_error'):
        st.error(st.session_state.pods_error)
        st.stop()

    pods = st.session_state.pods

    if not pods:
        st.success("🎉 当前集群没有异常Pod")
        st.stop()

    st.subheader("异常Pod列表")
    for pod in pods:
        cols = st.columns([3, 2, 2, 3])
        cols[0].write(f"📦 {pod['namespace']}")
        cols[1].write(f"📌 {pod['pod_name']}")
        cols[2].code(pod["status"])
        
        # 诊断按钮
        if cols[3].button("🔍 诊断", key=f"btn_{pod['namespace']}_{pod['pod_name']}"):
            with st.spinner("收集诊断信息中..."):
                diagnostic_data = get_pod_diagnostic_data(
                    st.session_state.api_client,
                    pod["namespace"], 
                    pod["pod_name"]
                )
            
            if "error" in diagnostic_data:
                st.error(diagnostic_data["error"])
            else:
                # 诊断结果展示
                with st.expander("📜 原始数据"):
                    st.json(diagnostic_data)
                
                with st.spinner("🤖 AI 分析中..."):
                    analysis = analyzer.analyze_pod(diagnostic_data)
                    
                with st.expander("💡 AI分析结果", expanded=True):
                    st.markdown(analysis)

elif selected_function == "应用状态探测":
    # ======================
    # 应用状态探测功能
    # ======================
    if selected_cluster == "请选择一个集群":
        st.info("请先选择一个集群")
        st.stop()

    st.subheader("应用Pod探测")

    # 获取全集群应用列表
    if 'all_applications' not in st.session_state or \
       st.session_state.get('apps_cluster') != selected_cluster:
        
        with st.spinner("⏳ 正在扫描全集群应用..."):
            try:
                st.session_state.all_applications = get_all_applications(st.session_state.api_client)
                st.session_state.apps_cluster = selected_cluster
                st.session_state.apps_error = None
            except Exception as e:
                st.session_state.apps_error = f"应用扫描失败: {str(e)}"
                st.session_state.all_applications = []

    if st.session_state.get('apps_error'):
        st.error(st.session_state.apps_error)
        st.stop()

    all_apps = st.session_state.all_applications
    if not all_apps:
        st.error("⚠️ 集群中没有发现部署应用")
        st.stop()

    # 应用搜索功能（新增状态绑定）
    search_term = st.text_input(
        "🔍 输入应用名称（支持模糊搜索）",
        value=st.session_state.get('app_search_term', ''),
        key='app_search_term'
    ).lower()
    
    app_options = [f"{app['name']} ::{app['namespace']}::" for app in all_apps]
    filtered_options = [opt for opt in app_options if search_term in opt.lower()]

    if not filtered_options:
        st.warning("没有找到匹配的应用")
        st.stop()

    # 应用选择框（新增状态绑定）
    selected_option = st.selectbox(
        "选择应用",
        filtered_options,
        index=0,  # 强制重置选择位置
        format_func=lambda x: x.replace("::", " ▸ ").replace("▸ ", "▸", 1),
        key='selected_app_option'
    )
    app_name, namespace = selected_option.split(" ::")[0], selected_option.split("::")[1]

    if st.button("🚀 开始探测", type="primary"):
        # 将应用探测状态存储到 st.session_state
        st.session_state.exploring_app = True
        st.session_state.exploring_app_name = app_name
        st.session_state.exploring_namespace = namespace

    # 检查是否正在探测某个应用
    if st.session_state.get("exploring_app", False):
        app_name = st.session_state["exploring_app_name"]
        namespace = st.session_state["exploring_namespace"]

        # 获取指定应用的Pod列表
        with st.spinner(f"🔭 正在获取 {app_name} 的Pod信息..."):
            pod_list = get_application_pods(
                st.session_state.api_client,
                namespace,
                app_name
            )
        
        if not pod_list:
            st.success("该应用没有运行中的Pod")
            # 探测结束，清除状态
            st.session_state.exploring_app = False
            st.stop()
            
        st.subheader("Pod列表")
        
        # 遍历Pods并创建诊断按钮
        for pod in pod_list:
            cols = st.columns([3, 2, 2, 3, 2])
            cols[0].write(f"📦 {pod['namespace']}")
            cols[1].write(f"📌 {pod['pod_name']}")
            cols[2].code(pod["status"])
            cols[3].write(f"🔄 重启 {pod['restart_count']} 次")
            
            # 确保诊断按钮具有唯一性
            btn_key = f"diag_{st.session_state['exploring_app_name']}_{pod['namespace']}_{pod['pod_name']}"
            if cols[4].button("🔍 诊断", key=btn_key):
                with st.spinner("收集诊断信息中..."):
                    diagnostic_data = get_pod_diagnostic_data(
                        st.session_state.api_client,
                        pod["namespace"], 
                        pod["pod_name"]
                    )
                
                if "error" in diagnostic_data:
                    st.error(diagnostic_data["error"])
                else:
                    with st.expander("📜 原始数据"):
                        st.json(diagnostic_data)
                    
                    with st.spinner("🤖 AI 分析中..."):
                        analysis = analyzer.analyze_pod(diagnostic_data)
                        
                    with st.expander("💡 AI分析结果", expanded=True):
                        st.markdown(analysis)

        st.stop()  # 避免页面重置到最初始状态
