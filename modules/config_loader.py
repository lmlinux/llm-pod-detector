import yaml
import streamlit as st
from pathlib import Path
from typing import Dict, Any

def load_configs() -> tuple:
    """加载所有配置文件"""
    try:
        config_path = Path(__file__).parent.parent / "config"
        
        # 加载集群配置
        clusters = []
        cluster_config = config_path / "clusters.yaml"
        if cluster_config.exists():
            with open(cluster_config, "r") as f:
                clusters = yaml.safe_load(f).get("clusters", [])
        if not clusters:
            st.error("集群配置文件中未找到有效的配置")
            st.stop()
            
        # 加载LLM配置
        llm_config = {}
        llm_file = config_path / "llm.yaml"
        if llm_file.exists():
            with open(llm_file, "r") as f:
                llm_config = yaml.safe_load(f).get("llm", {})
        if not llm_config.get("api_key"):
            st.error("LLM配置文件中未找到有效的API密钥")
            st.stop()
            
        return clusters, llm_config
        
    except FileNotFoundError as e:
        st.error(f"配置文件未找到: {str(e)}")
        st.stop()
    except Exception as e:
        st.error(f"配置加载失败: {str(e)}")
        st.stop()