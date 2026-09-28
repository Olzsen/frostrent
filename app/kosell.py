import httpx

class KOSellError(Exception): pass

class KOSellClient:
    def __init__(self,key,base): self.key=key; self.base=base.rstrip('/')
    def h(self, idem=None):
        h={"X-API-Key":self.key}
        if idem: h["Idempotency-Key"]=idem
        return h
    async def _req(self,method,path,**kwargs):
        async with httpx.AsyncClient(timeout=30) as c: r=await c.request(method,self.base+path,headers=self.h(kwargs.pop('idempotency_key',None)),**kwargs)
        if r.status_code>=400:
            try:
                d=r.json(); msg=(d.get('message') or d.get('detail') or d.get('error')) if isinstance(d,dict) else None
            except Exception: msg=None
            if r.status_code==401: raise KOSellError('Неверный KOSell API Key.')
            if r.status_code==403: raise KOSellError('KOSell отклонил доступ.')
            if r.status_code==429: raise KOSellError('Слишком много запросов к KOSell. Попробуйте позже.')
            if r.status_code==409: raise KOSellError('KOSell сообщил о конфликте операции.')
            raise KOSellError(f'KOSell HTTP {r.status_code}: {msg or "ошибка"}')
        return r.json()
    async def products(self,search=None):
        params={'search':search} if search else {}
        d=await self._req('GET','/api/v1/rental/products',params=params); return d if isinstance(d,list) else []
    async def balance(self): return await self._req('GET','/api/v1/account/balance')
    async def quote(self,pid,hours): return await self._req('POST','/api/v1/rental/calculate-price',json={'product_id':pid,'hours':hours})
    async def rent(self,pid,hours,currency,idem):
        return await self._req('POST','/api/v1/rental/rent',idempotency_key=idem,json={'product_id':pid,'hours':hours,'currency':currency,'idempotency_key':idem})
    async def credentials(self,uid): return await self._req('GET',f'/api/v1/rental/{uid}/credentials')
    async def code(self,uid): return await self._req('GET',f'/api/v1/rental/{uid}/code')
    async def active(self):
        d=await self._req('GET','/api/v1/rental/active'); return d if isinstance(d,list) else []
