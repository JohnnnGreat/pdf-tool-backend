from fastapi import APIRouter

from app.api.v1 import api_keys, auth, editor, health, pdf, convert, image, ocr, security, signature, document, generator, batch, utility, webhooks

router = APIRouter()

router.include_router(auth.router)
router.include_router(api_keys.router)
router.include_router(webhooks.router)
router.include_router(editor.router)
router.include_router(health.router, tags=["Health"])
router.include_router(pdf.router)
router.include_router(convert.router)
router.include_router(image.router)
router.include_router(ocr.router)
router.include_router(security.router)
router.include_router(signature.router)
router.include_router(document.router)
router.include_router(generator.router)
router.include_router(batch.router)
router.include_router(utility.router)
