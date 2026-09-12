"""
站点特征分析器
"""
from ..models import SiteType
from selectolax.parser import HTMLParser


class SiteProfiler:
    """站点类型识别器"""
    
    # SPA 框架特征
    SPA_MARKERS = [
        "vue.js", "react.js", "angular.js", "ng-app",
        "__NEXT_DATA__", "webpack", "app.js", "chunk.js"
    ]
    
    # API 端点特征
    API_MARKERS = [
        "application/json", "\"data\":", "\"code\":", "\"message\":"
    ]
    
    @staticmethod
    def profile(html: str, url: str, status_code: int) -> SiteType:
        """
        识别站点类型
        
        Args:
            html: HTML 内容
            url: URL
            status_code: HTTP 状态码
            
        Returns:
            站点类型
        """
        if status_code == 0:
            return SiteType.BLOCKED
        
        if status_code >= 400:
            return SiteType.BLOCKED
        
        if not html or len(html) < 100:
            return SiteType.BLOCKED
        
        html_lower = html.lower()
        
        # 检查是否是 API 响应
        if any(marker in html for marker in SiteProfiler.API_MARKERS):
            try:
                import json
                json.loads(html)
                return SiteType.API
            except:
                pass
        
        # 检查 SPA 特征
        if any(marker.lower() in html_lower for marker in SiteProfiler.SPA_MARKERS):
            # 进一步检查：如果有大量 <script> 但内容很少，很可能是 SPA
            try:
                parser = HTMLParser(html)
                scripts = parser.css("script")
                body_text = parser.css("body")
                
                if len(scripts) > 3 and body_text:
                    text_length = len(body_text[0].text(strip=True))
                    if text_length < 500:
                        return SiteType.SPA
            except:
                pass
        
        # 检查是否是 CMS（有常见的内容管理系统特征）
        try:
            parser = HTMLParser(html)
            links = parser.css("a[href]")
            
            if len(links) > 5:
                # 有合理数量的链接，可能是 CMS 或静态站点
                # 进一步检查动态特征
                forms = parser.css("form")
                if len(forms) > 0:
                    return SiteType.CMS
                
                # 检查常见 CMS 路径模式
                cms_patterns = [".aspx", ".jsp", ".php", "?id=", "&id="]
                for link in links[:20]:
                    href = link.attributes.get("href", "").lower()
                    if any(pattern in href for pattern in cms_patterns):
                        return SiteType.CMS
                
                # 默认为静态站点
                return SiteType.STATIC
        except:
            pass
        
        return SiteType.UNKNOWN
