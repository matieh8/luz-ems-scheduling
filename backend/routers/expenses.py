from datetime import datetime, timedelta
from typing import List, Optional
from collections import defaultdict
from io import StringIO
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from backend.database import get_db
from backend import models, schemas
from backend.tz import utcnow
import csv

router = APIRouter(prefix="/api/expenses", tags=["Expenses"])


def _month_bounds(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


@router.get("/", response_model=List[schemas.ExpenseResponse])
def list_expenses(year: Optional[int] = None, month: Optional[int] = None, category: Optional[str] = None,
                  from_date: Optional[datetime] = None, to_date: Optional[datetime] = None,
                  db: Session = Depends(get_db)):
    query = db.query(models.Expense)
    if year is not None and month is not None:
        start, end = _month_bounds(year, month)
        query = query.filter(models.Expense.date >= start, models.Expense.date < end)
    if from_date:
        query = query.filter(models.Expense.date >= from_date)
    if to_date:
        query = query.filter(models.Expense.date < to_date)
    if category:
        query = query.filter(func.lower(models.Expense.category) == func.lower(category))
    return query.order_by(models.Expense.date.desc(), models.Expense.id.desc()).all()


@router.get("/summary", response_model=schemas.ExpenseMonthSummary)
def expense_summary(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    now = utcnow()
    year = year or now.year
    month = month or now.month
    start, end = _month_bounds(year, month)
    expenses = db.query(models.Expense).filter(
        models.Expense.date >= start, models.Expense.date < end
    ).order_by(models.Expense.date.desc(), models.Expense.id.desc()).all()

    totals = defaultdict(lambda: {"total": 0.0, "count": 0})
    grand = 0.0
    for e in expenses:
        cat = e.category.strip() if e.category else "Uncategorised"
        totals[cat]["total"] += e.amount
        totals[cat]["count"] += 1
        grand += e.amount

    by_category = [schemas.ExpenseSummary(category=k, total=v["total"], count=v["count"])
                   for k, v in sorted(totals.items(), key=lambda x: -x[1]["total"])]

    return schemas.ExpenseMonthSummary(
        year=year, month=month,
        expenses=expenses,
        by_category=by_category,
        grand_total=grand
    )


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(models.Expense.category).distinct().all()
    return sorted({(r[0] or "").strip() for r in rows if r[0]})


@router.post("/", response_model=schemas.ExpenseResponse)
def create_expense(body: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    e = models.Expense(
        date=body.date,
        category=body.category.strip(),
        payment_method=(body.payment_method or "Card").strip(),
        amount=body.amount,
        notes=body.notes
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.put("/{expense_id}", response_model=schemas.ExpenseResponse)
def update_expense(expense_id: int, body: schemas.ExpenseUpdate, db: Session = Depends(get_db)):
    e = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    data = body.model_dump(exclude_unset=True)
    if "category" in data and data["category"]:
        data["category"] = data["category"].strip()
    if "payment_method" in data and data["payment_method"]:
        data["payment_method"] = data["payment_method"].strip()
    for k, v in data.items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return e


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    e = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(e)
    db.commit()
    return {"detail": "Expense deleted"}


@router.get("/export.csv", response_class=PlainTextResponse)
def export_csv(year: int = Query(...), month: int = Query(...), db: Session = Depends(get_db)):
    start, end = _month_bounds(year, month)
    expenses = db.query(models.Expense).filter(
        models.Expense.date >= start, models.Expense.date < end
    ).order_by(models.Expense.date.asc(), models.Expense.id.asc()).all()

    out = StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Category", "Type", "Item / Notes", "Amount"])
    for e in expenses:
        w.writerow([e.date.strftime("%Y-%m-%d"), e.category, e.payment_method or "Card", e.notes or "", f"{e.amount:.2f}"])
    total = sum(e.amount for e in expenses)
    w.writerow(["", "", "", "Total", f"{total:.2f}"])

    return PlainTextResponse(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=expenses-{year}-{month:02d}.csv"}
    )
