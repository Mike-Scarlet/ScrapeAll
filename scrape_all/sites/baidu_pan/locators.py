
# page identity (title based)
SITE_NAME = "百度网盘"
REQUIRE_PASSWORD_TITLE = "请输入提取码"

# shared link page - wait stable
SHARED_LINK_STABLE_SELECTOR = ".cazEfA, .wPQwLCb"

# shared link page - password submit
ACCESS_CODE_INPUT = "#accessCode"
SUBMIT_BTN = "#submitBtn"

# shared link page - breadcrumb & folder content
BREADCRUMB_HOLDER = ".FuIxtL"
BREADCRUMB_FULL_PATH = "li[node-type='tbAudfb']"
FOLDER_CONTENT = ".vdAfKMb"

# shared link page - file list
FILE_ICON_CLASS = "JS-fileicon"
ITEM_SELECTED_CLASS = "JS-item-active"
DIR_CLASS_MARKER = "dir"
LIST_HEADER = "ul.QAfdwP.tvPMvPb"
MULTI_SELECT_BUTTON = "span.zbyDdwb"
ITEM_SELECT_CHECKBOX = ".EOGexf"
RETURN_TO_PREV_TEXT = "返回上一级"

def file_link(name: str) -> str:
  return f"a.filename[title='{name}']"

FILE_ITEM_XPATH = "xpath=./ancestor::dd[1]"

# save dialog
SAVE_DIALOG = "#fileTreeDialog"
OPEN_SAVE_DIALOG_BUTTON = "div.bottom-save-path-icon"
TREE_ROOT_CONTENT = ".treeview-root-content"
DIALOG_CONFIRM_BTN = "a[node-type='confirm']"
DIALOG_CANCEL_BTN = "a[node-type='cancel']"
TREE_EXPAND_BTN = "em.plus.icon-operate"
TREE_LOADING = ".treeview-leaf-loading"
NEW_FOLDER_BTN = "a[title='新建文件夹']"
FOLDER_EDIT_INPUT = ".treeview-edit, input[type='text']"
DIALOG_ERROR = ".dialog-error, .error-msg, .tips-error"
SAVE_SUCCESS_XPATH = "xpath=//div[@class='info-section-title' and text()='保存成功']"

def tree_node_span(full_path: str) -> str:
  return f"span.treeview-txt[node-path='{full_path}']"

TREE_NODE_DIV_XPATH = "xpath=./ancestor::div[1]"

# save dialog - class markers (checked inside class attribute, not selectors)
TREE_NODE_EMPTY_CLASS = "treenode-empty"
TREE_NODE_EXPANDED_CLASS = "minus"
TREE_NODE_SELECTED_CLASS = "treeview-node-on"
