旧的顶层 `modules/` 与 `actions/` 目录保留为兼容层。

新的实现位于 `src/wanzhi/`：

- 语音：`src/wanzhi/voice/`
- 视觉：`src/wanzhi/vision/`
- Kivy UI：`src/wanzhi/ui/`
- 药物和紧急服务：`src/wanzhi/services/`

后续确认没有外部脚本引用旧路径后，可以删除旧目录。
