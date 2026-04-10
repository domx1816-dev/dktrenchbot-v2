
# Download endpoint for build archives
@app.get("/download/{filename}")
async def download_build(filename: str):
    from fastapi.responses import FileResponse
    import os
    file_path = os.path.join(os.path.dirname(__file__), "..", "state", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    return {"error": "File not found"}
