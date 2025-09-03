from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ..models import models, schemas, database
from ..services.auth import verify_token, create_access_token, get_password_hash, verify_password
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId


router = APIRouter()

def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON-serializable format"""
    if isinstance(doc, dict):
        return {
            key: str(value) if isinstance(value, ObjectId)
            else serialize_mongo_doc(value) if isinstance(value, (dict, list))
            else value
            for key, value in doc.items()
        }
    elif isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    return doc

@router.post("/create-admin")
async def create_admin(
    admin_data: schemas.UserCreate,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Create the single admin user - only one user allowed in the system"""
    # Check if any user already exists (since we only allow one user - the admin)
    existing_user = await db.users.find_one({})
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="A user already exists. Only one admin user is allowed in the system."
        )
    
    # Hash the password
    hashed_password = get_password_hash(admin_data.password)
    
    # Create admin user
    admin_user = {
        "email": admin_data.email,
        "name": admin_data.name,
        "is_admin": True,  # Force admin status
        "password_hash": hashed_password,
        "created_at": datetime.utcnow()
    }
    
    result = await db.users.insert_one(admin_user)
    created_admin = await db.users.find_one({"_id": result.inserted_id})
    
    # Remove password from response
    admin_response = serialize_mongo_doc(created_admin)
    admin_response.pop("password_hash", None)
    
    return {
        "message": "Admin created successfully",
        "admin": admin_response
    }

@router.get("/consultations")
async def list_consultations(
    skip: int = 0,
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(database.get_db),
    _: str = Depends(verify_token)
):
    """List all consultations (admin only)"""
    cursor = db.consultations.find({}).skip(skip).limit(limit).sort("created_at", -1)
    consultations = await cursor.to_list(length=limit)
    return {
        "consultations": serialize_mongo_doc(consultations),
        "total": len(consultations)
    }

@router.get("/consultations/{consultation_id}")
async def get_consultation(
    consultation_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db),
    _: str = Depends(verify_token)
):
    """Get detailed information about a specific consultation (admin only)"""
    if not ObjectId.is_valid(consultation_id):
        raise HTTPException(status_code=400, detail="Invalid consultation ID format")
    
    consultation = await db.consultations.find_one({"_id": ObjectId(consultation_id)})
    
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Get images for this consultation
    images = await db.consultation_images.find(
        {"consultation_id": ObjectId(consultation_id)}
    ).to_list(length=100)
    
    consultation_response = serialize_mongo_doc(consultation)
    consultation_response["images"] = serialize_mongo_doc(images)
    
    return {"consultation": consultation_response}

@router.delete("/consultations/{consultation_id}")
async def delete_consultation(
    consultation_id: str,
    db: AsyncIOMotorDatabase = Depends(database.get_db),
    _: str = Depends(verify_token)
):
    """Delete a specific consultation and all its associated data (admin only)"""
    if not ObjectId.is_valid(consultation_id):
        raise HTTPException(status_code=400, detail="Invalid consultation ID format")
    
    consultation_object_id = ObjectId(consultation_id)
    
    # Check if consultation exists
    consultation = await db.consultations.find_one({"_id": consultation_object_id})
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Delete associated images first
    images_result = await db.consultation_images.delete_many(
        {"consultation_id": consultation_object_id}
    )
    
    # Delete the consultation
    consultation_result = await db.consultations.delete_one({"_id": consultation_object_id})
    
    if consultation_result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Failed to delete consultation")
    
    return {
        "message": "Consultation deleted successfully",
        "consultation_id": consultation_id,
        "deleted_images": images_result.deleted_count
    }

@router.post("/login", response_model=schemas.Token)
async def admin_login(
    login_data: schemas.AdminLogin,
    db: AsyncIOMotorDatabase = Depends(database.get_db)
):
    """Admin login endpoint - single user system"""
    # Find the admin user (should be the only user in the system)
    admin_user = await db.users.find_one({
        "email": login_data.email,
        "is_admin": True
    })
    
    if not admin_user:
        raise HTTPException(
            status_code=401,
            detail="Admin user not found. Please create an admin first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(login_data.password, admin_user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": admin_user["email"], "is_admin": True}
    )
    return {"access_token": access_token, "token_type": "bearer"}

