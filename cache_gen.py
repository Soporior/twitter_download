import os
import pickle

class cache_gen():

    def __init__(self, save_path=None) -> None:
        # 统一使用根目录缓存，不再按用户分
        self.cache_path = os.path.join(os.getcwd(), "global_cache_data.log")

        # 迁移旧缓存（如果有的话）
        self.cache_data = set()
        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'rb') as f:
                self.cache_data = pickle.load(f)
        else:
            # 尝试从旧位置迁移缓存
            if save_path:
                old_cache_path = os.path.join(save_path, "cache_data.log")
                if os.path.exists(old_cache_path):
                    try:
                        with open(old_cache_path, 'rb') as f:
                            old_cache = pickle.load(f)
                            self.cache_data.update(old_cache)
                            print(f"[INFO] 已迁移旧缓存：{old_cache_path}")
                        # 保存迁移后的缓存
                        self._save()
                    except Exception as e:
                        print(f"[WARN] 迁移旧缓存失败: {e}")

    def _save(self):
        try:
            with open(self.cache_path, 'wb') as f:
                pickle.dump(self.cache_data, f)
        except Exception as e:
            print(f"[WARN] 保存缓存失败: {e}")

    def __del__(self):
        self._save()

    def add(self, element):
        self.cache_data.add(element)

    def is_present(self, element):
        if element in self.cache_data:
            return False
        else:
            self.add(element)
            return True


