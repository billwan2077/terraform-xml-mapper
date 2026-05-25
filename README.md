# Terraform &rarr; Cisco Network as Code XML Mapper

将 Cisco Catalyst Center Terraform 配置文件自动转换为 Cisco 标准 XML 格式的工具，附带 Web 交互界面。

## 功能

- **Terraform &rarr; XML 转换** &mdash; 解析 `.tf` 文件中的 `catalystcenter_fabric_*` 资源，按 Cisco API 字段命名生成 XML
- **Web 交互界面** &mdash; 上传/粘贴 Terraform 代码，可视化编辑参数，实时预览 XML
- **下拉选择** &mdash; 枚举值自动渲染为单选按钮（如 `authenticationProfileName`、`trafficType`）
- **布尔开关** &mdash; 布尔字段一键切换
- **XML 导出** &mdash; 复制到剪贴板或下载为 `.xml` 文件
- **CLI 模式** &mdash; 无需浏览器，命令行一键转换

## 快速开始

### 安装依赖

```bash
pip install fastapi uvicorn
```

### 启动 Web 界面

```bash
python3 app.py
# 访问 http://localhost:8000
```

### CLI 模式

```bash
python3 mapper.py path/to/your/terraform.tf
python3 mapper.py path/to/your/terraform.tf -o output_dir/
python3 mapper.py *.tf              # 批量转换
```

## 支持的资源 (SDA)

| Terraform Resource | XML Root | Cisco API Endpoint |
|---|---|---|
| `catalystcenter_fabric_site` | `<fabric-site>` | `/sda/fabricSites` |
| `catalystcenter_fabric_l2_virtual_network` | `<fabric-l2-virtual-network>` | `/sda/layer2VirtualNetworks` |
| `catalystcenter_fabric_l3_virtual_network` | `<fabric-l3-virtual-network>` | `/sda/layer3VirtualNetworks` |
| `catalystcenter_fabric_device` | `<fabric-device>` | `/sda/fabricDevices` |
| `catalystcenter_fabric_port_assignments` | `<fabric-port-assignments>` | `/sda/portAssignments` |
| `catalystcenter_fabric_zone` | `<fabric-zone>` | `/sda/fabricZones` |

## 项目结构

```
terraform-xml-mapper/
├── app.py                  # FastAPI Web 应用
├── mapper.py               # 核心转换引擎 (CLI + API)
├── mappings/
│   └── sda.json            # 映射模板 (资源属性 &rarr; XML 标签)
└── templates/
    └── index.html          # 单页 Web 前端
```

## 架构

```
┌──────────┐    ┌──────────────┐    ┌──────────┐
│ .tf 文件  │ -> │  mapper.py   │ -> │ XML 输出  │
│ 或粘贴    │    │  HCL解析     │    │          │
│          │    │  + 映射模板  │    │          │
└──────────┘    └──────┬───────┘    └──────────┘
                       │
                ┌──────┴───────┐
                │  app.py       │
                │  (FastAPI)    │
                └──────┬───────┘
                       │
                ┌──────┴───────┐
                │ index.html   │
                │  (Web UI)    │
                └──────────────┘
```

## 添加新的资源映射

编辑 `mappings/sda.json`，按以下格式添加：

```json
{
  "catalystcenter_fabric_xxx": {
    "xml_root": "fabric-xxx",
    "display_name": "Fabric XXX",
    "description": "...",
    "attributes": [
      {"tf_name": "field_name", "xml_tag": "fieldName", "type": "string", "required": true, "description": "..."},
      {"tf_name": "enum_field", "xml_tag": "enumField", "type": "enum", "required": true,
       "options": ["Option1", "Option2"], "description": "..."}
    ]
  }
}
```

## License

MIT
