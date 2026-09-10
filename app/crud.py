from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .db_models import Ticket
from .schemas import TicketRequest



def save_ticket(session: Session, ticket: TicketRequest) -> Ticket:
    try:
        db_ticket = Ticket(
            ticket_id=ticket.ticket_id,
            subject=ticket.subject,
            body=ticket.body,
            customer_id=ticket.customer_id
        )
        session.add(db_ticket)
        session.commit()
        session.refresh(db_ticket)
        return db_ticket
    except SQLAlchemyError as exc:
        session.rollback()
        raise
