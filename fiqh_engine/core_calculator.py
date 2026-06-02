from fractions import Fraction
from typing import List, Dict, Tuple
import re

class Heir:
    def __init__(self, name: str, share: Fraction, heir_type: str = "فرض"):
        self.name = name
        self.share = share
        self.type = heir_type

class FaraidCalculator:
    def __init__(self):
        self.estate = Fraction(1)

    def parse_heirs(self, text: str) -> List[Dict]:
        """تحليل نص عربي بسيط إلى ورثة"""
        text = text.strip()
        heirs = []

        # أمثلة بسيطة (يمكن توسيعها)
        patterns = [
            (r"زوجة", "زوجة", Fraction(1, 8)),
            (r"زوج", "زوج", Fraction(1, 4)),
            (r"أم", "أم", Fraction(1, 6)),
            (r"أب", "أب", Fraction(1, 6)),
            (r"بنات? (\d+)", "بنت", lambda m: Fraction(1, 2) if int(m.group(1)) == 1 else Fraction(2, 3)),
            (r"أولاد? (\d+)", "ابن", lambda m: Fraction(0)),  # عصبة
        ]

        for pattern, name, share in patterns:
            match = re.search(pattern, text)
            if match:
                if callable(share):
                    s = share(match)
                else:
                    s = share
                heirs.append({"name": name, "share": s, "count": int(match.group(1)) if match.lastindex else 1})

        # دعم العصبة (الأولاد)
        if "ابن" in text or "أولاد" in text:
            heirs.append({"name": "عصبة (أولاد)", "share": Fraction(0), "type": "عصبة"})

        return heirs

    def calculate(self, heirs_list: List[Dict]) -> Dict:
        """الحساب الرئيسي"""
        total_fixed = Fraction(0)
        asaba_share = Fraction(0)

        for h in heirs_list:
            if h.get("type") == "عصبة":
                asaba_share = Fraction(1) - total_fixed
            else:
                total_fixed += h["share"]

        # العول
        if total_fixed > 1:
            awl_factor = Fraction(1) / total_fixed
            for h in heirs_list:
                if h.get("type") != "عصبة":
                    h["share"] = h["share"] * awl_factor
            result = "تم تطبيق **العول**"
        else:
            result = "تم الحساب بدون عول"

        return {
            "heirs": heirs_list,
            "total_fixed": total_fixed,
            "awl_applied": total_fixed > 1,
            "result": result
        }

    def calculate_from_text(self, text: str) -> str:
        """الدالة الرئيسية التي يستدعيها الـ Agent"""
        heirs = self.parse_heirs(text)
        if not heirs:
            return "لم أتمكن من فهم الورثة في النص. جرب صيغة أوضح مثل: 'زوجة و3 أولاد وبنت وأم'"

        calc = self.calculate(heirs)

        explanation = f"""
**نتيجة حساب التركة:**

{text}

{calc['result']}

**الورثة:**
"""
        for h in calc['heirs']:
            explanation += f"- {h['name']}: {float(h['share']):.4f} ({h['share']})\n"

        explanation += f"\n{self.explain_awl() if calc['awl_applied'] else ''}"
        return explanation

    def explain_awl(self) -> str:
        return """
**العول** = التركة مش كفاية.
يعني الورثة عايزين أكتر من اللي موجود، فبنقلل نسبة كل واحد شوية عشان الفلوس تكفي.
مثال: زوجة + أم + أب → العول بيحصل.
"""

if __name__ == "__main__":
    calc = FaraidCalculator()
    print(calc.calculate_from_text("زوجة و3 أولاد وبنت وأم"))