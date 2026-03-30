from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.api.deps import get_db, require_admin
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.schemas.rule import RuleCreate, RuleRead, RuleUpdate
from wiregui.services.events import on_rule_created, on_rule_deleted

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/", response_model=list[RuleRead])
async def list_rules(
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await session.execute(select(Rule).order_by(Rule.inserted_at.desc()))
    return result.scalars().all()


@router.get("/{rule_id}", response_model=RuleRead)
async def get_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return rule


@router.post("/", response_model=RuleRead, status_code=201)
async def create_rule(
    body: RuleCreate,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rule = Rule(**body.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    logger.info("API: rule created {} -> {}", rule.action, rule.destination)
    await on_rule_created(rule)
    return rule


@router.put("/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: UUID,
    body: RuleUpdate,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, val)

    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rule = await session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    await session.delete(rule)
    await session.commit()
    logger.info("API: rule deleted {} {}", rule.action, rule.destination)
    await on_rule_deleted(rule)
