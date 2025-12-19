"""
性能测试
测试提示词管理系统的性能
"""
import pytest
import time
from infrastructure.prompts.manager import PromptManager


class TestPerformance:
    """性能测试"""
    
    def test_template_load_time(self):
        """测试模板加载时间"""
        manager = PromptManager()
        
        start_time = time.time()
        template = manager.load_template("blood_pressure_agent")
        load_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        assert template is not None
        assert load_time < 100, f"模板加载时间 {load_time}ms 超过100ms"
        print(f"模板加载时间: {load_time:.2f}ms")
    
    def test_prompt_render_time(self):
        """测试提示词渲染时间"""
        manager = PromptManager()
        
        start_time = time.time()
        prompt = manager.render("blood_pressure_agent")
        render_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        assert len(prompt) > 0
        assert render_time < 50, f"提示词渲染时间 {render_time}ms 超过50ms"
        print(f"提示词渲染时间: {render_time:.2f}ms")
    
    def test_cache_hit_rate(self):
        """测试缓存命中率"""
        manager = PromptManager()
        
        # 清除缓存
        manager.clear_all_cache()
        
        # 第一次渲染（未缓存）
        start_time = time.time()
        prompt1 = manager.render("blood_pressure_agent")
        time1 = (time.time() - start_time) * 1000
        
        # 第二次渲染（应该使用缓存）
        start_time = time.time()
        prompt2 = manager.render("blood_pressure_agent")
        time2 = (time.time() - start_time) * 1000
        
        assert prompt1 == prompt2
        assert time2 < time1, "缓存应该比首次加载快"
        print(f"首次渲染: {time1:.2f}ms, 缓存渲染: {time2:.2f}ms, 加速比: {time1/time2:.2f}x")
    
    def test_multiple_agents_performance(self):
        """测试多个Agent的性能"""
        manager = PromptManager()
        
        agent_keys = ["blood_pressure_agent", "appointment_agent", "router_tools"]
        
        start_time = time.time()
        for agent_key in agent_keys:
            prompt = manager.render(agent_key)
            assert len(prompt) > 0
        
        total_time = (time.time() - start_time) * 1000
        avg_time = total_time / len(agent_keys)
        
        assert avg_time < 50, f"平均渲染时间 {avg_time}ms 超过50ms"
        print(f"多个Agent平均渲染时间: {avg_time:.2f}ms")
