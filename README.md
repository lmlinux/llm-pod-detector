# llm-pod-detector 🩺⚡

The intelligent diagnostic AI doctor for Kubernetes Pods, analyzing cluster issues based on large language models. It supports multiple clusters, automatically collects diagnostic data, and displays AI diagnostic reports through a web interface.

## Features ✨
- 🕵️ Automatically collects complete diagnostic data for abnormal Pods:
  - Pod status (Status)
  - Kubernetes events (Events)
  - Previous container logs (Previous Logs)
  - Current container logs (Current Logs)
- 🤖 Performs intelligent root cause analysis using LLM
- 🌐 Supports management of multiple Kubernetes clusters
- 📊 Interactive web interface based on [Streamlit](https://github.com/streamlit/streamlit.git)
- 🐋 Ready-to-use containerized deployment with Docker

## Technology Stack 🛠️
- Web framework: Streamlit
- Kubernetes interaction: kubernetes-client
- AI integration: OpenAI API / LLM services compatible with OpenAI
- Containerization: Docker

## Quick Deployment 🚀

### Prerequisites
- Docker 20.10+
- Access to Kubernetes
- LLM API compatible with OpenAI

### Deployment Steps
```bash
# Clone the project repository
git clone https://github.com/lmlinux/llm-pod-detector.git
cd llm-pod-detector

# Add Kubernetes cluster information
vi config/clusters.yaml
# Add LLM API information compatible with OpenAI
vi config/llm.yaml

# Build Docker image
docker build -t llm-pod-detector:latest .

# Run container (default port 8501)
docker run -d --name llm-pod-detector -p 8501:8501 --restart unless-stopped llm-pod-detector:latest
```

## Direct Deployment Method Without Using Docker

### Prerequisites
- Python 3.13.0
- Access to Kubernetes
- LLM API compatible with OpenAI

### Deployment Steps
```bash
# Clone the project repository
git clone https://github.com/lmlinux/llm-pod-detector.git
cd llm-pod-detector

# Add Kubernetes cluster information
vi config/clusters.yaml

# Add LLM API information compatible with OpenAI
vi config/llm.yaml

# Install dependencies
pip install -r requirements.txt

# Start the application
streamlit run app.py
```

