import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor


# define wrapper function to use for I/O blocking code (any library that uses API Calls)
def run_in_threadpool_decorator(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix=name)
            return loop.run_in_executor(executor, func, *args, **kwargs)

        return wrapper

    return decorator
