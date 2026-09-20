"""
Seed script for Leadyfy OS.

Usage:
    python seed.py

Drops and recreates all tables, then inserts a realistic (fake) dataset
covering every module described in the spec, so the frontend developer can
immediately demo: dashboards, lists, filtering, search, relationships, and
workflows. No real personal information is used.
"""
import random
from datetime import date, datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models.base import (
    ClientStatus,
    CreatorAvailabilityStatus,
    EmployeeSubRole,
    ExpenseCategory,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    PayoutStatus,
    ScriptStatus,
    ShootStatus,
    SupportTicketStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    VideoStatus,
)
from app.models.client import Asset, Client
from app.models.creator import Creator, CreatorAvailability
from app.models.finance import CreatorPayout, Expense, Payment
from app.models.order import Order
from app.models.script import Script
from app.models.shoot import Shoot
from app.models.system import ActivityLog, Notification, SupportTicket
from app.models.task import Task
from app.models.user import Employee, User
from app.models.video import Video, VideoFeedback
from app.utils.security import hash_password

now = datetime.now(timezone.utc)
today = date.today()


def reset_database():
    print("Dropping and recreating all tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def make_user(db, email, full_name, role, sub_role=None):
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    employee = None
    if role in (UserRole.OWNER, UserRole.ADMIN, UserRole.EMPLOYEE):
        employee = Employee(
            user_id=user.id,
            sub_role=sub_role or EmployeeSubRole.GENERAL,
            phone=f"+91-9{random.randint(100000000, 999999999)}",
            salary=random.choice([35000, 45000, 60000, 90000, 150000]),
            joining_date=today - timedelta(days=random.randint(30, 900)),
            is_active=True,
        )
        db.add(employee)
        db.flush()
    return user, employee


def seed():
    db = SessionLocal()
    try:
        # --- Users / Employees -------------------------------------------------
        owner_user, owner_emp = make_user(db, "owner@leadyfy.com", "Ananya Rao", UserRole.OWNER)
        admin_user, admin_emp = make_user(db, "admin@leadyfy.com", "Rahul Mehta", UserRole.ADMIN)

        sales_user, sales_emp = make_user(
            db, "sales@leadyfy.com", "Priya Nair", UserRole.EMPLOYEE, EmployeeSubRole.SALES
        )
        writer_user, writer_emp = make_user(
            db, "writer@leadyfy.com", "Karan Shah", UserRole.EMPLOYEE, EmployeeSubRole.SCRIPT_WRITER
        )
        writer2_user, writer2_emp = make_user(
            db, "writer2@leadyfy.com", "Neha Kapoor", UserRole.EMPLOYEE, EmployeeSubRole.SCRIPT_WRITER
        )
        shoot_mgr_user, shoot_mgr_emp = make_user(
            db, "shootmanager@leadyfy.com", "Vikram Singh", UserRole.EMPLOYEE, EmployeeSubRole.SHOOT_MANAGER
        )
        editor_user, editor_emp = make_user(
            db, "editor@leadyfy.com", "Simran Kaur", UserRole.EMPLOYEE, EmployeeSubRole.EDITOR
        )
        editor2_user, editor2_emp = make_user(
            db, "editor2@leadyfy.com", "Arjun Verma", UserRole.EMPLOYEE, EmployeeSubRole.EDITOR
        )
        db.commit()

        # --- Creators ------------------------------------------------------------
        creators_data = [
            ("Ishaan Malhotra", "Male", "18-24", "Hindi,English", "Mumbai", "Fashion,Lifestyle"),
            ("Riya Desai", "Female", "18-24", "English,Gujarati", "Ahmedabad", "Beauty,Skincare"),
            ("Aditya Kulkarni", "Male", "25-34", "Marathi,Hindi,English", "Pune", "Tech,Gadgets"),
            ("Sanya Kapoor", "Female", "18-24", "Hindi,English", "Delhi", "Food,Travel"),
            ("Rohan Iyer", "Male", "25-34", "Tamil,English", "Chennai", "Fitness,Sports"),
            ("Meera Pillai", "Female", "25-34", "Malayalam,English", "Kochi", "Parenting,Home"),
        ]
        creators = []
        for name, gender, age_group, langs, loc, niches in creators_data:
            creator = Creator(
                name=name,
                gender=gender,
                age_group=age_group,
                languages=langs,
                location=loc,
                niches=niches,
                demographics=f"{age_group} {gender.lower()} audience, urban {loc}",
                contact=f"+91-9{random.randint(100000000, 999999999)}",
                rates=random.choice([5000, 8000, 12000, 15000, 20000]),
                bank_upi_info=f"{name.split()[0].lower()}@upi",
                portfolio_links=f"https://instagram.com/{name.split()[0].lower()}",
                availability_status=CreatorAvailabilityStatus.AVAILABLE,
            )
            db.add(creator)
            creators.append(creator)
        db.flush()

        for creator in creators:
            for i in range(5):
                db.add(
                    CreatorAvailability(
                        creator_id=creator.id,
                        date=today + timedelta(days=i * 2),
                        status=random.choice(
                            [CreatorAvailabilityStatus.AVAILABLE, CreatorAvailabilityStatus.AVAILABLE, CreatorAvailabilityStatus.BOOKED]
                        ),
                    )
                )
        db.commit()

        # --- Clients ---------------------------------------------------------------
        clients_data = [
            ("Glowick Cosmetics", "Glowick Pvt Ltd", "hello@glowick.com", "Beauty", ClientStatus.ACTIVE),
            ("Urban Threads", "Urban Threads Fashion LLP", "contact@urbanthreads.com", "Fashion", ClientStatus.ACTIVE),
            ("FitFuel Nutrition", "FitFuel India Pvt Ltd", "team@fitfuel.in", "Health & Wellness", ClientStatus.ACTIVE),
            ("ByteWave Electronics", "ByteWave Technologies", "info@bytewave.com", "Consumer Tech", ClientStatus.ONBOARDING),
            ("SpiceRoute Foods", "SpiceRoute Foods Pvt Ltd", "hi@spiceroute.com", "Food & Beverage", ClientStatus.NEW),
            ("PawCare Essentials", "PawCare Pvt Ltd", "support@pawcare.com", "Pet Care", ClientStatus.LEAD),
            ("Nestwell Home Decor", "Nestwell Interiors", "sales@nestwell.com", "Home & Living", ClientStatus.ON_HOLD),
            ("Trailblaze Outdoors", "Trailblaze Gear Co", "team@trailblaze.com", "Outdoor & Adventure", ClientStatus.COMPLETED),
        ]
        clients = []
        employees_pool = [sales_emp, admin_emp]
        for client_name, company, email, industry, status_ in clients_data:
            client = Client(
                client_name=client_name,
                company_name=company,
                email=email,
                phone=f"+91-8{random.randint(100000000, 999999999)}",
                whatsapp=f"+91-8{random.randint(100000000, 999999999)}",
                brand_name=client_name,
                industry=industry,
                gst_tax_id=f"29GSTIN{random.randint(1000,9999)}Z",
                source=random.choice(["Referral", "Instagram Ads", "Inbound Website", "Cold Outreach"]),
                assigned_employee_id=random.choice(employees_pool).id,
                status=status_,
                notes="Demo seed record.",
            )
            db.add(client)
            clients.append(client)
        db.flush()

        for client in clients[:3]:
            db.add(Asset(client_id=client.id, name="Brand Guidelines", file_url="https://example.com/assets/brand-guidelines.pdf", asset_type="brand_guideline"))
            db.add(Asset(client_id=client.id, name="Logo Pack", file_url="https://example.com/assets/logo-pack.zip", asset_type="logo"))
        db.commit()

        # Give the first client portal access, for frontend demo purposes.
        portal_client = clients[0]
        portal_user = User(
            email=portal_client.email,
            hashed_password=hash_password("Password123!"),
            full_name=portal_client.client_name,
            role=UserRole.CLIENT,
            is_active=True,
        )
        db.add(portal_user)
        db.flush()
        portal_client.user_id = portal_user.id
        db.commit()

        # --- Orders ------------------------------------------------------------------
        orders = []
        for client in clients:
            for _ in range(random.choice([1, 1, 2])):
                video_count = random.choice([5, 10, 15, 20])
                pricing = video_count * random.choice([3000, 4000, 5000])
                gst = round(pricing * 0.18, 2)
                total = round(pricing + gst, 2)
                received = round(total * random.choice([0, 0.3, 0.5, 1.0]), 2)
                order = Order(
                    client_id=client.id,
                    package_name=f"{random.choice(['Starter', 'Growth', 'Premium'])} UGC Package",
                    contracted_video_count=video_count,
                    pricing=pricing,
                    gst_tax=gst,
                    total_invoice_amount=total,
                    amount_received=received,
                    start_date=today - timedelta(days=random.randint(5, 60)),
                    due_date=today + timedelta(days=random.randint(10, 45)),
                    assigned_employee_id=random.choice(employees_pool).id,
                    status=random.choice(list(OrderStatus)),
                )
                db.add(order)
                orders.append(order)
        db.commit()

        # --- Scripts -------------------------------------------------------------------
        scripts = []
        writers = [writer_emp, writer2_emp]
        for order in orders:
            for video_number in range(1, min(order.contracted_video_count, 4) + 1):
                writer = random.choice(writers)
                status_ = random.choice(list(ScriptStatus))
                script = Script(
                    client_id=order.client_id,
                    order_id=order.id,
                    video_number=video_number,
                    writer_id=writer.id,
                    language=random.choice(["English", "Hindi", "Hinglish"]),
                    script_text="[Demo script content — hook, product highlight, CTA]",
                    reference_links="https://example.com/reference",
                    deadline=now + timedelta(days=random.randint(1, 14)),
                    revision_count=random.randint(0, 2),
                    comments="Looks good, minor tone tweak requested." if status_ == ScriptStatus.REVISION_REQUIRED else None,
                    status=status_,
                )
                db.add(script)
                scripts.append(script)
        db.commit()

        # --- Shoots --------------------------------------------------------------------
        shoots = []
        for order in orders:
            for _ in range(random.choice([1, 2])):
                shoot_date = now + timedelta(days=random.randint(-5, 20))
                creator = random.choice(creators)
                shoot = Shoot(
                    client_id=order.client_id,
                    order_id=order.id,
                    date_time=shoot_date,
                    location=random.choice(["Mumbai Studio A", "Client Office", "Outdoor - Marine Drive", "Pune Studio B"]),
                    creator_id=creator.id,
                    cameraman="Freelance Cameraman Pool",
                    shoot_manager_id=shoot_mgr_emp.id,
                    shooting_assistant="Assistant on call",
                    special_notes="Bring product samples.",
                    status=random.choice(list(ShootStatus)),
                    checklist_script_approved=True,
                    checklist_creator_confirmed=True,
                )
                db.add(shoot)
                shoots.append(shoot)
        db.commit()

        # --- Videos ----------------------------------------------------------------------
        editors = [editor_emp, editor2_emp]
        videos = []
        for order in orders:
            related_scripts = [s for s in scripts if s.order_id == order.id]
            related_shoots = [s for s in shoots if s.order_id == order.id]
            for script in related_scripts:
                status_ = random.choice(list(VideoStatus))
                editor = random.choice(editors)
                video = Video(
                    client_id=order.client_id,
                    order_id=order.id,
                    script_id=script.id,
                    creator_id=script.creator_id or random.choice(creators).id,
                    shoot_id=random.choice(related_shoots).id if related_shoots else None,
                    assigned_editor_id=editor.id,
                    deadline=now + timedelta(days=random.randint(-3, 10)),
                    video_file_link="https://drive.google.com/demo-raw-cut" if status_ != VideoStatus.SCRIPT_APPROVED else None,
                    thumbnail_url="https://example.com/thumb.jpg",
                    revision_count=random.randint(0, 2),
                    final_delivery_link="https://drive.google.com/demo-final" if status_ == VideoStatus.DELIVERED else None,
                    delivered_at=now - timedelta(days=random.randint(1, 5)) if status_ == VideoStatus.DELIVERED else None,
                    status=status_,
                )
                db.add(video)
                videos.append(video)
        db.commit()

        for video in videos:
            if video.status in (VideoStatus.REVISION, VideoStatus.DELIVERED, VideoStatus.FINAL_APPROVED):
                db.add(
                    VideoFeedback(
                        video_id=video.id,
                        client_id=video.client_id,
                        feedback_text="Loved the energy! Please trim the intro by 2 seconds." if video.status == VideoStatus.REVISION else "Approved, looks great!",
                        revision_requested=(video.status == VideoStatus.REVISION),
                    )
                )
        db.commit()

        # --- Tasks -----------------------------------------------------------------------
        assignees = [sales_emp, writer_emp, writer2_emp, shoot_mgr_emp, editor_emp, editor2_emp, admin_emp]
        task_titles = [
            "Follow up with client on outstanding invoice",
            "Confirm creator availability for next week",
            "Review Q3 production performance report",
            "Update client brand kit with new logo",
            "Prepare shoot checklist for upcoming session",
            "Chase editor for overdue video revision",
            "Onboard new client onto the portal",
        ]
        for title in task_titles:
            db.add(
                Task(
                    title=title,
                    description="Demo seed task.",
                    assignee_id=random.choice(assignees).id,
                    priority=random.choice(list(TaskPriority)),
                    deadline=now + timedelta(days=random.randint(-2, 10)),
                    status=random.choice(list(TaskStatus)),
                )
            )
        db.commit()

        # --- Payments ----------------------------------------------------------------------
        for order in orders:
            if order.amount_received > 0:
                pending = round(order.total_invoice_amount - order.amount_received, 2)
                status_ = (
                    PaymentStatus.PAID
                    if pending <= 0
                    else PaymentStatus.PARTIALLY_PAID
                )
                db.add(
                    Payment(
                        order_id=order.id,
                        client_id=order.client_id,
                        invoice_amount=order.total_invoice_amount,
                        amount_received=order.amount_received,
                        payment_date=today - timedelta(days=random.randint(1, 20)),
                        method=random.choice(["Bank Transfer", "UPI", "Cheque"]),
                        transaction_ref=f"TXN{random.randint(100000, 999999)}",
                        status=status_,
                    )
                )
        db.commit()

        # --- Expenses ------------------------------------------------------------------------
        expense_rows = [
            (ExpenseCategory.SALARIES, 420000, "Monthly payroll run"),
            (ExpenseCategory.STUDIO, 25000, "Studio rental - Mumbai"),
            (ExpenseCategory.EQUIPMENT, 18000, "Camera lens rental"),
            (ExpenseCategory.OFFICE, 12000, "Office supplies & internet"),
            (ExpenseCategory.FUEL, 4500, "Shoot location travel"),
        ]
        for category, amount, notes in expense_rows:
            db.add(
                Expense(
                    category=category,
                    amount=amount,
                    user_id=admin_user.id,
                    date=today - timedelta(days=random.randint(1, 25)),
                    notes=notes,
                )
            )
        db.commit()

        # --- Creator Payouts -----------------------------------------------------------------
        for creator in creators[:4]:
            order = random.choice(orders)
            video_count = random.randint(1, 4)
            rate = creator.rates or 8000
            db.add(
                CreatorPayout(
                    creator_id=creator.id,
                    order_id=order.id,
                    video_count=video_count,
                    contracted_rate=rate,
                    total_payout=round(video_count * rate, 2),
                    payment_date=today - timedelta(days=random.randint(1, 15)) if random.random() > 0.5 else None,
                    reference=f"PAYOUT{random.randint(1000,9999)}",
                    status=random.choice(list(PayoutStatus)),
                )
            )
        db.commit()

        # --- Support Tickets -------------------------------------------------------------------
        for client in random.sample(clients, 4):
            db.add(
                SupportTicket(
                    client_id=client.id,
                    subject=random.choice(
                        ["Question about invoice", "Need to reschedule shoot", "Video download link not working", "Request for extra revision"]
                    ),
                    description="Demo seed support ticket.",
                    status=random.choice(list(SupportTicketStatus)),
                )
            )
        db.commit()

        # --- Notifications (a handful for the owner/admin) --------------------------------------
        for uid in (owner_user.id, admin_user.id, sales_user.id, writer_user.id, editor_user.id):
            db.add(
                Notification(
                    user_id=uid,
                    type=random.choice(list(NotificationType)),
                    title="Welcome to Leadyfy OS",
                    message="Your account has been provisioned. Explore the dashboard to get started.",
                    is_read=False,
                )
            )
        db.commit()

        # --- Activity log sample -----------------------------------------------------------------
        db.add(ActivityLog(user_id=owner_user.id, action="system.seed", entity_type="System", details="Demo data seeded."))
        db.commit()

        print("\nSeed complete.\n")
        print("Demo credentials (all passwords: Password123!):")
        print("  Owner          -> owner@leadyfy.com")
        print("  Admin          -> admin@leadyfy.com")
        print("  Sales          -> sales@leadyfy.com")
        print("  Script Writer  -> writer@leadyfy.com / writer2@leadyfy.com")
        print("  Shoot Manager  -> shootmanager@leadyfy.com")
        print("  Editor         -> editor@leadyfy.com / editor2@leadyfy.com")
        print(f"  Client Portal  -> {portal_client.email}")
        print(f"\nSeeded: {len(clients)} clients, {len(orders)} orders, {len(scripts)} scripts, "
              f"{len(shoots)} shoots, {len(videos)} videos, {len(creators)} creators.")

    finally:
        db.close()


if __name__ == "__main__":
    reset_database()
    seed()
