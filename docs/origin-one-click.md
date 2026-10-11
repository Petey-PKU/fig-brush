# Origin 一键套用格式：用户路径设计

## 目标

用户不需要打开 PowerShell，也不需要理解 JSON。参考图片由 fig-brush 生成一次格式包；在 Origin 中激活自己的图后，右键选择一次“粘贴参考格式”即可把外观套用到当前图。

## 推荐交互

1. 在 fig-brush 中选择参考 PNG/JPEG。系统生成一个格式包，其中 `format_parameters.json` 是机器可读参数，`reference_analysis.json` 是复核记录。
2. 当前版本不需要用户运行脚本：在 Codex 对话中说“把这个格式参数粘贴到当前 Origin 图”，系统调用 active-graph bridge 连接已经打开的 Origin。用户只需要提供 `format_parameters.json` 的位置。
3. 目标桌面版是一次安装 Origin 扩展（`.opx`）。安装方式是把 `.opx` 拖到 Origin 窗口；Origin 官方的 Package Manager 会注册菜单和脚本。安装后，在 Origin 中打开自己的 `.opju`，点击目标 Graph 使其激活，在图层空白处或曲线上右键，选择 `Fig-brush → 粘贴参考格式`。
4. 扩展弹出文件选择框，用户选择格式包中的 `format_parameters.json`。扩展在当前 Origin 进程中直接设置页面、图层、坐标轴和字体，并支持 Origin 的撤销；默认不保存项目，用户确认后再按 Origin 的保存命令。
5. Origin 中检查数据绑定、图例、坐标范围和统计内容。格式刷只修改视觉属性，无法从截图可靠判断的科研数据和统计设置保持用户原值。

如果输出目录中已经有 native 参考项目（例如显式请求 native render 后生成的
`result.opju`），还可以让 Codex 调用 `stage_format_clipboard`。它会打开这个
只含合成占位数据的参考项目，把 Origin 自己的格式剪贴板准备好；用户切回自己的
项目后，直接使用 Origin 原生右键 **粘贴格式**。这个动作依赖 Origin 的会话剪贴板，
需要在粘贴完成前保持 Origin 打开，且不会保存或覆盖任一项目。

## 真正的右键入口如何实现

Origin 的标准 `复制格式` / `粘贴格式` 只理解 Origin 内部对象、主题和剪贴板格式，不能直接读取外部 JSON。右键扩展需要随 `.opx` 安装一个 X-Function，并在 `ContextMenus.xml` 注册 Graph Page 和 Plot Line 的菜单项。X-Function 调用 Origin Embedded Python 或 Origin C 读取 JSON，然后通过当前 Graph/Page 的属性 setter 应用格式；必要时可以在本机把对象格式保存为 Origin 的 `.oth` 主题，再调用 `GraphPage.ApplyFormat(..., undo=true)`。

`.oth` 与 Origin 版本及图形对象类型相关，应由用户本机的 Origin 运行时生成，不能在项目外部凭空序列化。因此 JSON 仍然是跨版本的格式参数源，`.oth` 是本机缓存或可选复用主题。

这一方案保留 Origin 原生右键体验，同时避免改写 Origin 数据。扩展应至少注册两个入口：图层/空白区域（页面、轴、字体）和曲线对象（线宽、颜色、符号）；未匹配的对象只提示复核，不覆盖数据。`.opx` 需要在目标 Origin 版本中用 Package Manager 打包并做实机验证，未验证前不要把它当作已发布安装包。

## 没有扩展时

打开输出文件夹里的 `APPLY_FORMAT.md`，按表格在 Origin 的 Format/Page、Format/Layer、Format/Axes 和 Plot Details 中设置。这个手动路径是兼容方案，不要求用户阅读两个 JSON。

## 安全约束

- 格式参数默认只包含视觉信息，不读取或上传用户工作表数据。
- 应用时不自动覆盖输入项目；建议先保存副本，确认后由用户执行 Origin 的保存命令。
- 无法从图片可靠判断的内容（数据、统计、拟合、轴范围、图例语义）保持用户原值，并在结果中提示复核。

## 官方依据

- [在产品菜单中放置 X-Function](https://docs.originlab.com/x-function/guide/putting-an-x-function-in-the-product-menu/)
- [GraphPage.ApplyFormat](https://docs.originlab.com/originc/ref/originobject-applyformat/)
- [分享图形设置和主题](https://docs.originlab.com/quick-help/share-graph-settings/)
- [Origin 复制/粘贴格式](https://docs.originlab.com/origin-help/copypaste-format/)
