# redis_tasks.py
import json
import uuid
from typing import Dict, Any, List
from datetime import datetime
import asyncio
from redis import Redis

class RedisTaskQueue:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.tasks_prefix = "task:"
        self.queue_key = "task_queue"
        self.results_prefix = "task_result:"
        
        # ✅ KORJAUS: Pidempi TTL (7 päivää)
        self.task_ttl = 86400 * 7  # 7 days (604800 seconds)
        self.result_ttl = 86400 * 7  # 7 days
        
    def create_task(self, task_type: str, data: Dict[str, Any], username: str) -> str:
        """Luo uusi task ja palauttaa task_id"""
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "task_type": task_type,
            "data": data,
            "username": username,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "progress": 0,
            "total": data.get("total", 1)
        }
        
        # ✅ KORJAUS: Käytä pidempi TTL
        self.redis.setex(
            f"{self.tasks_prefix}{task_id}",
            self.task_ttl,  # 7 days instead of 1 hour
            json.dumps(task_data)
        )
        
        # Lisää queueun
        self.redis.rpush(self.queue_key, task_id)
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Hae taskin tila"""
        data = self.redis.get(f"{self.tasks_prefix}{task_id}")
        if not data:
            return {"status": "not_found"}
        
        task_data = json.loads(data)
        
        # ✅ LISÄYS: Lisää results suoraan statukseen
        results = self.get_results(task_id)
        task_data["results"] = results
        
        return task_data
    
    def update_task(self, task_id: str, updates: Dict[str, Any]):
        """Päivitä taskin tila"""
        task_data = self.get_task_status(task_id)
        if task_data.get("status") == "not_found":
            return False
        
        task_data.update(updates)
        task_data["updated_at"] = datetime.now().isoformat()
        
        # ✅ KORJAUS: Päivitä TTL samalla
        self.redis.setex(
            f"{self.tasks_prefix}{task_id}",
            self.task_ttl,
            json.dumps(task_data)
        )
        return True
    
    def add_result(self, task_id: str, result: Dict[str, Any]):
        """Lisää tulos taskiin"""
        results_key = f"{self.results_prefix}{task_id}"
        current = self.redis.get(results_key)
        
        if current:
            results = json.loads(current)
        else:
            results = []
        
        results.append(result)
        
        # ✅ KORJAUS: Käytä pidempi TTL
        self.redis.setex(results_key, self.result_ttl, json.dumps(results))
        
        # Päivitä progress
        task_data = self.get_task_status(task_id)
        if task_data.get("status") != "not_found":
            progress = len(results)
            total = task_data.get("total", 1)
            
            updates = {
                "progress": progress,
                "status": "completed" if progress >= total else "running"
            }
            self.update_task(task_id, updates)
    
    def get_results(self, task_id: str) -> List[Dict[str, Any]]:
        """Hae kaikki tulokset"""
        data = self.redis.get(f"{self.results_prefix}{task_id}")
        return json.loads(data) if data else []
    
    def check_user_active_tasks(self, username: str) -> int:
        """Montako aktiivista taskia käyttäjällä on"""
        count = 0
        for key in self.redis.scan_iter(f"{self.tasks_prefix}*"):
            data = self.redis.get(key)
            if not data:
                continue
            task = json.loads(data)
            if (task.get("username") == username and 
                task.get("status") in ["pending", "running"]):
                count += 1
        return count

    # ✅ LISÄYS: Helper metodi TTL:n tarkistamiseen (debugging)
    def get_task_ttl(self, task_id: str) -> int:
        """Palauttaa montako sekuntia taskilla on TTL jäljellä"""
        return self.redis.ttl(f"{self.tasks_prefix}{task_id}")
