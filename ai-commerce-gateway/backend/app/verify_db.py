import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
sys.path.append('/buyer-client')
from mcp_client import MCPClient
from scripted_buyer import run_buyer
from app.models import AuditLogModel

mcp = MCPClient('http://localhost:8000/mcp')
engine = create_engine('postgresql+psycopg://acg_user:acg_pass@postgres:5432/ai_commerce_gateway')
Session = sessionmaker(bind=engine)
db = Session()

print('\n==== 1. RUNNING CANONICAL APPROVED FLOW ====')
receipt1 = run_buyer('Find me running shoes under 6000', mcp)
tx1 = receipt1.get('transaction_id')

print('\n==== 2. RUNNING CANONICAL BLOCKED FLOW ====')
receipt2 = run_buyer('Buy the 8999 Velocity Pro Premium footwear', mcp)
tx2 = receipt2.get('transaction_id')

print('\n==== 3. VERIFYING DB RECORDS ====')

def print_audit_trail(tx_id, label):
    if not tx_id:
        print(f'No tx_id for {label}')
        return
    
    payment_log = db.query(AuditLogModel).filter_by(transaction_id=tx_id).first()
    if not payment_log:
        print(f'No payment log found for {tx_id}')
        return
    cart_id = payment_log.cart_id
    
    print(f'\n--- AUDIT TRAIL FOR {label} (tx: {tx_id}, cart: {cart_id}) ---')
    logs = db.query(AuditLogModel).filter_by(cart_id=cart_id).order_by(AuditLogModel.timestamp.asc()).all()
    for idx, log in enumerate(logs):
        print(f'{idx+1}. [{log.stage}] actor={log.actor} tx={log.transaction_id}')
        if log.stage == 'decision_engine':
            payload = log.payload
            has_reasoning = 'reasoning' in payload
            print(f'   -> has_reasoning: {has_reasoning}')
            if has_reasoning:
                r = payload['reasoning']
                print(f'   -> customer_request: {r.get("customer_request")}')
                print(f'   -> considered_count: {r.get("considered_count")}')
                print(f'   -> why: {r.get("why")}')

print_audit_trail(tx1, 'APPROVED FLOW (₹5998)')
print_audit_trail(tx2, 'BLOCKED FLOW (₹8999)')
