import asyncio
import logging
from typing import Optional, Tuple
from playwright.async_api import Page, Locator, TimeoutError, ElementHandle

class SharedLinkSaver:
  def __init__(self, page: Page):
    self.page = page
  
  async def has_save_dialog(self) -> bool:
    try:
      await self.page.wait_for_selector("#fileTreeDialog", timeout=100)
      return True
    except TimeoutError:
      return False
  
  async def open_save_dialog(self):
    if await self.has_save_dialog():
      return
    
    save_button = self.page.locator("div.bottom-save-path-icon").first
    await save_button.click()
    await self.page.wait_for_selector(".treeview-root-content", timeout=10000)
    
    # await self.page.wait_for_load_state("load")
    # await self.page.wait_for_selector("#fileTreeDialog", state="visible", timeout=10000)
  
  async def confirm_selection(self) -> bool:
    dialog = await self._get_dialog()
    if not dialog:
      return False
    
    try:
      confirm_btn = dialog.locator("a[node-type='confirm']").first
      await confirm_btn.click()
      await asyncio.sleep(2.0)
      
      try:
        success_element = await self.page.wait_for_selector(
          "xpath=//div[@class='info-section-title' and text()='保存成功']",
          timeout=8000
        )
        if success_element:
          return True
      except TimeoutError:
        logging.error("cannot find save success")
        return False
        
    except Exception as e:
      logging.error(f"click confirm button failed: {e}")
      return False
    
    return False
  
  async def cancel_selection(self) -> bool:
    dialog = await self._get_dialog()
    if not dialog:
      return False
    
    try:
      cancel_btn = dialog.locator("a[node-type='cancel']").first
      await cancel_btn.click()
      await self.page.wait_for_selector("#fileTreeDialog", state="detached", timeout=5000)
      # await self.page.wait_for_timeout(500)
      # await self.page.wait_for_load_state("load")
      return True
    except Exception as e:
      logging.error(f"click cancel button failed: {e}")
      return False
  
  async def navigate_to_path(self, target_path: str, create_if_missing: bool = True) -> Tuple[bool, str]:
    parts = [""] + [p for p in target_path.strip("/").split("/")]
    parent_node_path = None
    
    try:
      # fast skip
      last_visible_index = -1
      for i, part in enumerate(parts):
        if i == 0:
          target_node_path = "/"
        else:    
          target_node_path = "/".join(parts[:i+1])
        
        if await self._has_element_node(target_node_path):
          last_visible_index = i
          parent_node_path = target_node_path
      
      for i, part in enumerate(parts):
        if i <= last_visible_index:
          continue
        
        if i == 0:
          target_node_path = "/"
        else:    
          target_node_path = "/".join(parts[:i+1])
        
        logging.info(f"parent -> target: {parent_node_path} -> {target_node_path}")
        
        if parent_node_path and await self._has_element_node(parent_node_path):
          await self._ensure_node_select_and_expanded(parent_node_path)
        
        if await self._has_element_node(target_node_path):
          parent_node_path = target_node_path
        elif create_if_missing:
          child_node = await self._create_folder(part, parent_node_path)
          if child_node:
            parent_node_path = target_node_path
          else:
            return False, f"创建文件夹失败: {part}"
        else:
          return False, f"路径不存在: {target_node_path}"
      
      # if target_path:
      await self._ensure_node_select_and_expanded(target_path)
      
      return True, f"成功导航到: {target_path}"
      
    except Exception as e:
      return False, f"导航失败: {str(e)}"
  
  async def _get_dialog(self) -> Optional[Locator]:
    try:
      await self.page.wait_for_selector("#fileTreeDialog", state="visible", timeout=5000)
      return self.page.locator("#fileTreeDialog")
    except TimeoutError:
      logging.error("cannot find file tree dialog")
      return None
  
  async def _has_element_node(self, full_path: str) -> bool:
    return await self._find_element_node_by_full_path(full_path) is not None
  
  async def _find_element_node_by_full_path(self, full_path: str) -> Optional[Locator]:
    try:
      node_path_span_element = self.page.locator(f"span.treeview-txt[node-path='{full_path}']").first
      if await node_path_span_element.is_visible():
        node_div_element = node_path_span_element.locator("xpath=./ancestor::div[1]")
        return node_div_element
    except Exception as e:
      # logging.debug(f"找不到节点路径 {full_path}: {e}")
      pass
    return None
  
  async def _ensure_node_select_and_expanded(self, path: str):
    # logging.info(f"do select and expand path: {path}")
    while True:
      parent_div_element = await self._find_element_node_by_full_path(path)
      if not parent_div_element:
        break
      
      try:
        need_click = False
        
        parent_class = await parent_div_element.get_attribute("class")
        expandible = "treenode-empty" not in parent_class
        
        expand_btn = parent_div_element.locator("em.plus.icon-operate").first
        if await expand_btn.is_visible():
          expand_btn_class = await expand_btn.get_attribute("class")
        
        if expandible and "minus" not in expand_btn_class:
          need_click = True
        
        if "treeview-node-on" not in parent_class:
          need_click = True
        
        if need_click:
          # print("need click")
          await expand_btn.click()
          await self.page.wait_for_timeout(500)
          loading_locator = self.page.locator(".treeview-leaf-loading")
          if await loading_locator.count() > 0:
            await self.page.wait_for_selector(".treeview-leaf-loading", state="detached", timeout=10000)
          # await self.page.wait_for_load_state("load")
        else:
          # print("no need click")
          break
          
      except Exception as e:
        logging.error(f"expand error: {e}")
        import traceback
        traceback.print_exc()
        break
        
    # logging.info(f"end of do select and expand path: {path}")
  
  async def _create_folder(self, new_folder_name: str, parent_node_path: Optional[str]) -> Optional[Locator]:
    logging.info(f"create folder: {new_folder_name} (path: {parent_node_path})")
    
    try:
      await self._ensure_node_select_and_expanded(parent_node_path)
      
      new_folder_btn = self.page.locator("a[title='新建文件夹']").first
      await new_folder_btn.wait_for(state="visible", timeout=5000)
      await new_folder_btn.click()
      
      edit_input = await self._find_edit_input()
      
      if edit_input:
        await edit_input.clear()
        await edit_input.fill(new_folder_name)
        await edit_input.press("Enter")
        await self._wait_till_no_edit_input()
        await self.page.wait_for_timeout(500)
        
        # print("start wait for idle")
        # await self.page.wait_for_load_state("load")
        # print("end wait for idle")
        
        error_msg = await self._check_for_error()
        # print("end check for error")
        if error_msg:
          logging.error(f"创建文件夹失败: {error_msg}")
          
      if parent_node_path:
        new_path = f"{parent_node_path.rstrip('/')}/{new_folder_name}"
        return await self._find_element_node_by_full_path(new_path)
      
    except Exception as e:
      logging.error(f"创建文件夹过程中出错: {e}")
    
    return None
  
  async def _find_edit_input(self) -> Optional[Locator]:
    try:
      await self.page.wait_for_selector(
        ".treeview-edit, input[type='text']", 
        timeout=3000
      )
      return self.page.locator(".treeview-edit, input[type='text']").first
    except TimeoutError:
      return None
    
  async def _wait_till_no_edit_input(self):
    try:
      await self.page.wait_for_selector(
        ".treeview-edit, input[type='text']", 
        state="detached",
        timeout=3000
      )
    except TimeoutError:
      raise RuntimeError("still exist text input")
  
  async def _check_for_error(self) -> Optional[str]:
    try:
      error_elem = self.page.locator(".dialog-error, .error-msg, .tips-error").first
      if await error_elem.is_visible():
        return await error_elem.text_content()
    except:
      pass
    
    return None