"""
Cache manager for FPL API responses.

This module provides functionality to cache API responses locally and manage their expiry.
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class CacheManager:
    def __init__(self, cache_dir: str, cache_expiry_hours: int = 3):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory to store cache files
            cache_expiry_hours: Number of hours after which cache should be considered stale
        """
        self.cache_dir = cache_dir
        self.cache_expiry = timedelta(hours=cache_expiry_hours)
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _get_cache_path(self, endpoint: str) -> str:
        """Get the full path for a cache file."""
        return os.path.join(self.cache_dir, f"{endpoint}.json")
    
    def get_cached_response(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response if it exists and is not expired.
        
        Args:
            endpoint: API endpoint identifier (e.g., 'static' or 'fixtures')
            
        Returns:
            Cached data if valid, None otherwise
        """
        cache_path = self._get_cache_path(endpoint)
        
        if not os.path.exists(cache_path):
            return None
            
        try:
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)
                
            # Check if cache has expired
            cached_time = datetime.fromtimestamp(cached_data['cached_at'])
            if datetime.now() - cached_time > self.cache_expiry:
                return None
                
            return cached_data['data']
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # If there's any issue with the cache file, ignore it
            return None
    
    def save_response(self, endpoint: str, data: Dict[str, Any]) -> None:
        """
        Save API response to cache.
        
        Args:
            endpoint: API endpoint identifier
            data: Response data to cache
        """
        cache_path = self._get_cache_path(endpoint)
        
        cache_data = {
            'cached_at': time.time(),
            'data': data
        }
        
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f)
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                os.remove(os.path.join(self.cache_dir, filename))
