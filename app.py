# app.py
import streamlit as st
from modules.config_loader import load_configs
from modules.k8s_utils import *
from modules.llm_analyzer import LLMAnalyzer
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    layout="wide",
    page_title="K8s集群诊断",
    page_icon="🔍",
    initial_sidebar_state="expanded"
)

# 初始化配置
clusters, llm_config = load_configs()
analyzer = LLMAnalyzer(llm_config)

# 页面布局
st.title("K8s 集群诊断工具")

# ==========================
# 侧边栏布局
# ==========================
with st.sidebar:
    selected_function = st.radio(
        "选择功能",
        ["异常Pod诊断", "应用状态探测", "集群概览"],
        index=0
    )

    if selected_function != "集群概览":
        selected_cluster = st.radio(
            "选择集群",
            ["请选择一个集群"] + [c["cluster_name"] for c in clusters]
        )
    else:
        selected_cluster = None

# ==========================
# 公共逻辑：集群连接
# ==========================
if selected_function != "集群概览" and selected_cluster != "请选择一个集群":
    current_cluster = next(c for c in clusters if c["cluster_name"] == selected_cluster)
    
    if 'prev_cluster' not in st.session_state or st.session_state.prev_cluster != selected_cluster:
        with st.spinner(f"正在连接集群 {selected_cluster}..."):
            st.session_state.api_client = create_k8s_client(
                current_cluster["api_url"],
                current_cluster["token"]
            )
            st.session_state.prev_cluster = selected_cluster
            
            states_to_clear = [
                'pods', 'all_applications',
                'exploring_app', 'exploring_app_name', 'exploring_namespace', 'exploring_app_kind',
                'app_search_term', 'selected_app_option'
            ]
            for state in states_to_clear:
                if state in st.session_state:
                    del st.session_state[state]

# ==========================
# 页面状态清理逻辑
# ==========================
if 'active_function' not in st.session_state:
    st.session_state.active_function = selected_function

if st.session_state.active_function != selected_function:
    st.session_state.active_function = selected_function

    states_to_clear = [
        'pods', 'all_applications', 'cluster_stats',
        'apps_cluster', 'apps_error', 'pods_error',
        'exploring_app', 'exploring_app_name', 'exploring_namespace', 'exploring_app_kind'
    ]
    for state in states_to_clear:
        if state in st.session_state:
            del st.session_state[state]

# ==========================
# 功能路由
# ==========================
if selected_function == "异常Pod诊断":
    if selected_cluster == "请选择一个集群":
        st.info("请先选择一个集群")
        st.stop()

    refresh_flag = False
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button('🔄 刷新列表'):
            refresh_flag = True
            if 'pods' in st.session_state:
                del st.session_state.pods  # 修正后的行

    if 'pods' not in st.session_state or refresh_flag or st.session_state.get('pods_cluster') != selected_cluster:
        with st.spinner("正在获取集群状态..."):
            try:
                st.session_state.pods = get_non_running_pods(st.session_state.api_client)
                st.session_state.pods_cluster = selected_cluster
                st.session_state.pods_error = None
            except Exception as e:
                st.session_state.pods_error = f"集群连接失败: {str(e)}"
                st.session_state.pods = []

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
        cols[0].write(f"🏢 {pod['namespace']}")
        cols[1].write(f"🐳 {pod['pod_name']}")
        cols[2].code(pod["status"])
        
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
                with st.expander("📜 原始数据"):
                    st.json(diagnostic_data)
                
                with st.spinner("🤖 AI 分析中..."):
                    analysis = analyzer.analyze_pod(diagnostic_data)
                    
                with st.expander("💡 AI分析结果", expanded=True):
                    st.markdown(analysis)

elif selected_function == "应用状态探测":
    if selected_cluster == "请选择一个集群":
        st.info("请先选择一个集群")
        st.stop()

    st.subheader("应用Pod探测")

    if 'all_applications' not in st.session_state or st.session_state.get('apps_cluster') != selected_cluster:
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

    search_term = st.text_input(
        "🔍 输入应用名称（支持模糊搜索）",
        value=st.session_state.get('app_search_term', ''),
        key='app_search_term'
    ).lower()
    
    app_options = [
    f"{app['name']}::{app['namespace']}::{app['kind']}"  # 修改分隔符为::
    for app in all_apps
    ]
    filtered_options = [opt for opt in app_options if search_term in opt.lower()]

    if not filtered_options:
        st.warning("没有找到匹配的应用")
        st.stop()

    selected_option = st.selectbox(
    "选择应用",
    filtered_options,
    index=0,
    format_func=lambda x: x.replace("::", " ▸ ").replace("▸ ", "▸", 1),
    key='selected_app_option'
    )
    app_name, namespace, kind = selected_option.split("::", 2)  # 使用::分割，最多分割两次
    
    if st.button("🚀 获取Pod列表", type="primary"):
        st.session_state.exploring_app = True
        st.session_state.exploring_app_name = app_name
        st.session_state.exploring_namespace = namespace
        st.session_state.exploring_app_kind = kind

    if st.session_state.get("exploring_app", False):
        app_name = st.session_state["exploring_app_name"]
        namespace = st.session_state["exploring_namespace"]
        kind = st.session_state["exploring_app_kind"]

        with st.spinner(f"🔭 正在获取 {app_name} 的Pod信息..."):
            pod_list = get_application_pods(
                st.session_state.api_client,
                namespace,
                app_name,
                kind
            )
        
        if not pod_list:
            st.success("该应用没有运行中的Pod")
            st.session_state.exploring_app = False
            st.stop()
            
        st.subheader("Pod列表")
        
        for pod in pod_list:
            cols = st.columns([3, 2, 2, 3, 2])
            cols[0].write(f"🏢 {pod['namespace']}")
            cols[1].write(f"🐳 {pod['pod_name']}")
            cols[2].code(pod["status"])
            cols[3].write(f"🔄 重启 {pod['restart_count']} 次")
            
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

        st.stop()

elif selected_function == "集群概览":
    st.subheader("全局集群概览")
    
    refresh_flag = False
    if st.button('🔄 刷新集群状态'):
        refresh_flag = True
        if 'cluster_stats' in st.session_state:
            del st.session_state.cluster_stats
    
    if 'cluster_stats' not in st.session_state or refresh_flag:
        all_stats = []
        with st.spinner("正在扫描所有集群..."):
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                for idx, cluster in enumerate(clusters):
                    futures.append(executor.submit(
                        lambda c, i: (i, get_cluster_summary(c)),
                        cluster,
                        idx
                    ))
                
                temp_results = []
                for future in as_completed(futures):
                    try:
                        index, result = future.result()
                        temp_results.append( (index, result) )
                    except Exception as e:
                        st.error(f"集群扫描失败: {str(e)}")
                
                temp_results.sort(key=lambda x: x[0])
                all_stats = [result for (index, result) in temp_results]

        st.session_state.cluster_stats = all_stats
    
    total_stats = {
        "nodes": 0,
        "pods": 0,
        "deployments": 0,
        "statefulsets": 0,
        "errors": 0
    }
    
    valid_clusters = []
    for stats in st.session_state.cluster_stats:
        if stats["status"] == "success":
            total_stats["nodes"] += stats["nodes"]
            total_stats["pods"] += stats["pods"]
            total_stats["deployments"] += stats["deployments"]
            total_stats["statefulsets"] += stats["statefulsets"]
            valid_clusters.append(stats)
        else:
            total_stats["errors"] += 1
      
    cols = st.columns(5)
    cols[0].metric("🌐 集群总数", len(clusters), delta_color="off")
    cols[1].metric("🖥️ 总节点数", total_stats["nodes"])
    cols[2].metric("🐳 总Pod数", total_stats["pods"])
    cols[3].metric("🚀 总无状态应用", total_stats["deployments"])
    cols[4].metric("🔒 总有状态应用", total_stats["statefulsets"])
    
    st.divider()
    
    st.subheader("分集群详情")
    
    col1, col2 = st.columns([1,4])
    with col1:
        show_healthy = st.checkbox("显示健康集群", value=True)
    with col2:
        show_problems = st.checkbox("显示异常集群", value=True)
    
    for stats in st.session_state.cluster_stats:
        if stats["status"] == "error" and not show_problems:
            continue
        if stats["status"] == "success" and not show_healthy:
            continue
        
        with st.container():
            cols = st.columns([2,1,1,1,1,3])
            
            status_icon = "✅" if stats["status"] == "success" else "❌"
            cols[0].subheader(f"{status_icon} {stats['cluster_name']}")
            
            if stats["status"] == "success":
                cols[1].metric("节点", stats["nodes"])
                cols[2].metric("Pods", stats["pods"])
                cols[3].metric("Deploy", stats["deployments"])
                cols[4].metric("Stateful", stats["statefulsets"])
                cols[5].code(f"更新时间: {stats['timestamp']}")
            else:
                cols[1].error("连接失败")
                cols[2].error("N/A")
                cols[3].error("N/A")
                cols[4].error("N/A")
                cols[5].error(stats["error"])
            
            st.divider()