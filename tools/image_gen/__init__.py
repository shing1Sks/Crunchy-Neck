"""tools/image_gen — image generation via Gemini."""
from .image_gen_tool import image_gen_command
from .image_gen_types import ImageGenParams

TOOL_DEFINITION = {
    "name": "image_gen",
    "description": (
        "Generate an image from a text prompt using Gemini "
        "(gemini-3.1-flash-image-preview) and save it as a PNG.\n\n"
        "Returns the workspace-relative path to the saved image.\n\n"
        "Rules:\n"
        "- Requires GEMINI_API_KEY in the environment or in a .env file at the workspace root.\n"
        "- Default size is 512px (supported by gemini-3.1-flash-image-preview).\n"
        "- Image is saved to .agent/images/ with a timestamp filename.\n"
        "- Use send_user_media() with media_type='photo' to send the image to the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Text description of the image to generate.",
            },
            "size": {
                "type": "integer",
                "default": 512,
                "description": "Image resolution in pixels. Default 512.",
            },
            "aspect_ratio": {
                "type": "string",
                "default": "1:1",
                "enum": ["1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2"],
                "description": "Aspect ratio of the generated image. Default '1:1'.",
            },
        },
        "required": ["prompt"],
    },
}

__all__ = ["image_gen_command", "ImageGenParams", "TOOL_DEFINITION"]
