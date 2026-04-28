from fastapi import APIRouter

from app.api.v1 import (
    ai, api_keys, auth, batch, billing, convert, dashboard, document, editor,
    generator, health, image, jobs, ocr, pdf, results, security, signature,
    utility, webhooks,
)

router = APIRouter()

router.include_router(auth.router)
router.include_router(ai.router)
router.include_router(api_keys.router)
router.include_router(billing.router)
router.include_router(dashboard.router)
router.include_router(jobs.router)
router.include_router(results.router)
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
