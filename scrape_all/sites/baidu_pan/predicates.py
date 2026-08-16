
from playwright.async_api import Page

async def WaitForBaidupanSharedLinkStable(page: Page, timeout: int = 10000):
  # print("in WaitForBaidupanSharedLinkStable")
  await page.wait_for_selector('.cazEfA, .wPQwLCb', state='visible', timeout=timeout)
  # print("out WaitForBaidupanSharedLinkStable")
  
# # 定义两个等待任务
# task_load = asyncio.create_task(page.wait_for_load_state("domcontentloaded"))
# task_selector = asyncio.create_task(page.wait_for_selector('.cazEfA, .wPQwLCb', state='visible', timeout=timeout))

# # 使用 return_when=asyncio.FIRST_COMPLETED
# # 只要其中一个条件满足，就会继续向下执行
# done, pending = await asyncio.wait(
#     [task_load, task_selector], 
#     return_when=asyncio.FIRST_COMPLETED
# )

# # 习惯性操作：取消掉还没完成的任务，避免后台继续跑浪费资源
# for task in pending:
#     task.cancel()