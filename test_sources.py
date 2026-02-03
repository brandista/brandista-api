import asyncio
import httpx
import re

async def test_ytj():
    print("\n--- Testing YTJ API ---")
    business_id = "0116754-4" # Valio
    variations = [
        f"https://avoindata.prh.fi/opendata-ytj-api/v3/companies?businessId={business_id}",
        f"https://avoindata.prh.fi/opendata/bis/v1/{business_id}",
        f"https://avoindata.prh.fi/opendata-ytj-api/v3/companies?name=Valio%20Oy"
    ]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in variations:
            print(f"Requesting: {url}")
            try:
                resp = await client.get(url)
                print(f"Status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    total = data.get('totalResults', 0)
                    print(f"✅ Total Results: {total}")
                    if total > 0:
                        companies = data.get('companies', [])
                        if companies:
                            import json
                            print(f"✅ First Result JSON:\n{json.dumps(companies[0], indent=2, ensure_ascii=False)}")
                            # Stop after first success
                            break
                else:
                    print(f"❌ Failed: {resp.text[:100]}")
            except Exception as e:
                print(f"⚠️ Error: {e}")

async def test_kauppalehti():
    print("\n--- Testing Kauppalehti Scraping ---")
    business_id = "1610416-3"
    clean_id = business_id.replace('-', '')
    url = f"https://www.kauppalehti.fi/yritykset/yritys/{clean_id}"
    print(f"Requesting: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            print(f"Final URL: {resp.url}")
            if resp.status_code == 200:
                print(f"✅ Success! Page length: {len(resp.text)}")
                terms = ["Liikevaihto", "Liikev.", "Henkilöstö", "Henkilöstömäärä", "Tulos", "M€", "K€", "EUR"]
                for term in terms:
                    if term in resp.text:
                        print(f"✅ Found '{term}' in text!")
                    else:
                        print(f"❌ '{term}' NOT found")
                
                # Print a snippet of where Liikevaihto might be
                idx = resp.text.lower().find("liikevaihto")
                if idx != -1:
                    print(f"\nContext around 'Liikevaihto':\n{resp.text[idx-50:idx+200]}")
                
                # Check for bot detection
                if "captcha" in resp.text.lower() or "forbidden" in resp.text.lower():
                    print("⚠️ Likely BOT DETECTION hit")
            else:
                print(f"❌ Failed: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ytj())
    asyncio.run(test_kauppalehti())
