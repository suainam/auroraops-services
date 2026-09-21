#!/usr/bin/env python3
"""
OpenViking MCP Server - 使用 FastMCP
提供工具让 AI Agent 调用 OpenViking 的语义搜索功能
"""

import os
import sys
import logging
import requests
from mcp.server.fastmcp import FastMCP

# 配置日志 (STDIO 模式必须用 stderr)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openviking_mcp")

# OpenViking 配置
VIKING_HOST = os.environ.get("VIKING_HOST", "127.0.0.1")
VIKING_PORT = os.environ.get("VIKING_PORT", "30012")
VIKING_BASE_URL = f"http://{VIKING_HOST}:{VIKING_PORT}"

# 初始化 FastMCP
mcp = FastMCP("openviking")


@mcp.tool()
async def viking_search(query: str, top_k: int = 5) -> str:
    """搜索 OpenViking 知识库中的相关内容。
    
    Args:
        query: 搜索查询语句
        top_k: 返回结果数量，默认 5
    """
    logger.info(f"Searching for: {query}")
    
    try:
        response = requests.post(
            f"{VIKING_BASE_URL}/api/v1/search/find",
            json={"query": query, "top_k": top_k},
            timeout=30
        )
        result = response.json()
        
        if result.get("status") == "ok":
            data = result.get("result", {})
            resources = data.get("resources", [])
            
            if not resources:
                return "未找到相关内容"
            
            output = ["搜索结果:\n"]
            for i, r in enumerate(resources[:top_k], 1):
                abstract = r.get("abstract", "")
                score = r.get("score", 0)
                uri = r.get("uri", "")
                output.append(f"{i}. [{score:.3f}] {uri}\n   {abstract[:200]}...")
            
            return "\n".join(output)
        else:
            return f"搜索失败: {result}"
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return f"搜索出错: {str(e)}"


@mcp.tool()
async def viking_add_resource(path: str) -> str:
    """向 OpenViking 添加资源（文件、目录或 URL）以便后续搜索。
    
    Args:
        path: 资源路径，可以是本地文件、目录或 URL
    """
    logger.info(f"Adding resource: {path}")
    
    try:
        response = requests.post(
            f"{VIKING_BASE_URL}/api/v1/resources",
            json={"path": path},
            timeout=30
        )
        result = response.json()
        
        if result.get("status") == "ok":
            data = result.get("result", {})
            status = data.get("status", "")
            if status == "success":
                return f"✅ 资源添加成功: {path}"
            else:
                errors = data.get("errors", [])
                return f"⚠️ {errors}"
        else:
            return f"添加失败: {result}"
            
    except Exception as e:
        logger.error(f"Add resource error: {e}")
        return f"添加出错: {str(e)}"


@mcp.tool()
async def viking_health() -> str:
    """检查 OpenViking 服务健康状态"""
    try:
        response = requests.get(f"{VIKING_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return "✅ OpenViking 服务正常"
        else:
            return f"⚠️ 服务异常: {response.status_code}"
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return f"❌ 服务不可用: {str(e)}"


def main():
    """主入口"""
    logger.info("Starting OpenViking MCP Server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
