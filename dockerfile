
FROM python:3.13.0

# 设置工作目录
WORKDIR /app

# 将Pipfile和Pipfile.lock复制到工作目录
COPY requirements.txt ./

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将项目文件复制到工作目录
COPY . .

# 暴露Streamlit应用默认端口
EXPOSE 8501

# 设置环境变量
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

# 运行Streamlit应用
CMD ["streamlit", "run", "app.py"]