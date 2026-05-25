#!/usr/bin/env python3
"""
Terraform → Cisco Network as Code XML Mapper — Web App
FastAPI backend with single-page HTML frontend.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Add parent dir to path for mapper import
sys.path.insert(0, str(Path(__file__).parent))
from mapper import load_mappings, parse_tf, tf_to_xml, get_resource_mapping

app = FastAPI(title="Terraform → Cisco XML Mapper")

# Load mappings at startup
MAPPINGS = load_mappings()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page."""
    html = (Path(__file__).parent / "templates" / "index.html").read_text()
    return html


@app.post("/api/parse")
async def parse_tf_file(file: Optional[UploadFile] = File(None),
                         content: Optional[str] = Form(None)):
    """
    Parse Terraform content and return structured resource data
    along with mapping metadata for form rendering.
    """
    tf_text = None

    if file:
        tf_text = (await file.read()).decode("utf-8")
    elif content:
        tf_text = content

    if not tf_text:
        return JSONResponse({"error": "No Terraform content provided"}, status_code=400)

    try:
        resources = parse_tf(tf_text)
    except Exception as e:
        return JSONResponse({"error": f"Failed to parse Terraform: {str(e)}"}, status_code=400)

    # Enrich resources with mapping metadata
    enriched = []
    for res in resources:
        mapping = get_resource_mapping(MAPPINGS, res["type"])
        if mapping:
            # Add available resource types for dropdown
            resource_types = _get_supported_types()
            enriched.append({
                "type": res["type"],
                "name": res["name"],
                "display_name": mapping.get("display_name", res["type"]),
                "description": mapping.get("description", ""),
                "xml_root": mapping.get("xml_root", ""),
                "attributes": res["attributes"],
                "attr_defs": mapping.get("attributes", []),
                "mapped": True
            })
        else:
            enriched.append({
                "type": res["type"],
                "name": res["name"],
                "display_name": res["type"],
                "description": "",
                "attributes": res["attributes"],
                "attr_defs": [],
                "mapped": False
            })

    return JSONResponse({
        "resources": enriched,
        "resource_types": _get_supported_types()
    })


@app.post("/api/convert")
async def convert_to_xml(resource_type: str = Form(...),
                         resource_name: str = Form(...),
                         attrs_json: str = Form(...)):
    """
    Convert attributes to XML using the specified resource type mapping.
    """
    try:
        attrs = json.loads(attrs_json)
    except json.JSONDecodeError as e:
        return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)

    xml = tf_to_xml(resource_type, attrs, MAPPINGS)
    if xml is None:
        return JSONResponse({"error": f"No mapping found for {resource_type}"}, status_code=400)

    return PlainTextResponse(xml, media_type="application/xml")


@app.get("/api/types")
async def get_resource_types():
    """Get all supported resource types with their mapping details."""
    types = _get_supported_types()
    return JSONResponse({"resource_types": types})


def _get_supported_types() -> list:
    """Get all supported resource types with their attribute definitions."""
    types = []
    for provider_data in MAPPINGS.values():
        for res_type, mapping in provider_data.get("resources", {}).items():
            types.append({
                "type": res_type,
                "display_name": mapping.get("display_name", res_type),
                "description": mapping.get("description", ""),
                "xml_root": mapping.get("xml_root", ""),
                "attributes": mapping.get("attributes", [])
            })
    return types


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚀 Starting Terraform → Cisco XML Mapper on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
