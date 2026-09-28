from dataclasses import dataclass
@dataclass
class Order:
    product_id:int; product_name:str; hours:int; quote:dict; price_rub:float
ORDERS={}
