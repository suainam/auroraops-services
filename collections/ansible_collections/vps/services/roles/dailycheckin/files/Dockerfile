FROM sitoi/dailycheckin:latest

# 升级依赖
# 注意：使用 --no-cache-dir 减少镜像大小
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade dailycheckin

COPY patch_dailycheckin_message.py /tmp/patch_dailycheckin_message.py
RUN python /tmp/patch_dailycheckin_message.py && rm -f /tmp/patch_dailycheckin_message.py

COPY patch_dailycheckin_bilibili_nulls.py /tmp/patch_dailycheckin_bilibili_nulls.py
RUN python /tmp/patch_dailycheckin_bilibili_nulls.py && rm -f /tmp/patch_dailycheckin_bilibili_nulls.py

# 设置工作目录（虽然 dailycheckin 使用 entrypoint，但保留良好习惯）
WORKDIR /dailycheckin

# 验证安装 (dailycheckin 不支持 --version 参数，改用 pip show)
RUN pip show dailycheckin

# 清理 pip 缓存进一步减小体积
RUN rm -rf /root/.cache/pip
