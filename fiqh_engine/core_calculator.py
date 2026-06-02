from fractions import Fraction
import re
from typing import List, Dict

class Heir:
    def __init__(self, name: str, share: Fraction, count: int = 1, heir_type: str = "فرض"):
        self.name = name
        self.share = share
        self.count = count
        self.type = heir_type

class FaraidCalculator:
    def __init__(self):
        pass

    def parse_heirs(self, text: str) -> List[Dict]:
        """تحليل النص العربي واستخراج الورثة"""
        text = text.strip()
        heirs = []

        # زوج / زوجة
        if "زوجة" in text:
            heirs.append({"name": "زوجة", "share": Fraction(1, 8), "count": 1, "type": "فرض"})
        if "زوج" in text:
            heirs.append({"name": "زوج", "share": Fraction(1, 4), "count": 1, "type": "فرض"})

        # أم / أب
        if "أم" in text:
            heirs.append({"name": "أم", "share": Fraction(1, 6), "count": 1, "type": "فرض"})
        if "أب" in text:
            heirs.append({"name": "أب", "share": Fraction(1, 6), "count": 1, "type": "فرض"})

        # بنات
        match = re.search(r"(\d+)?\s*بنات?", text)
        if match:
            count = int(match.group(1)) if match.group(1) else 1
            share = Fraction(1, 2) if count == 1 else Fraction(2, 3)
            heirs.append({"name": "بنت", "share": share, "count": count, "type": "فرض"})

        # أولاد (عصبة)
        match = re.search(r"(\d+)?\s*أولاد?|ابن", text)
        if match:
            count = int(match.group(1)) if match.group(1) else 1
            heirs.append({"name": "ابن", "share": Fraction(0), "count": count, "type": "عصبة"})

        return heirs

    def calculate(self, heirs: List[Dict]) -> Dict:
        """الحساب الكامل للفرائض + العصبة + العول"""
        total_fixed = Fraction(0)
        asaba_count = 0

        for h in heirs:
            if h["type"] == "فرض":
                total_fixed += h["share"]
            else:
                asaba_count = h["count"]

        awl_applied = False
        if total_fixed > 1:
            awl_factor = Fraction(1) / total_fixed
            for h in heirs:
                if h["type"] == "فرض":
                    h["share"] = h["share"] * awl_factor
            awl_applied = True

        # توزيع العصبة
        remaining = Fraction(1) - sum(h["share"] for h in heirs if h["type"] == "فرض")
        if remaining > 0 and asaba_count > 0:
            for h in heirs:
                if h["type"] == "عصبة":
                    h["share"] = remaining

        return {
            "heirs": heirs,
            "awl_applied": awl_applied,
            "total_fixed_before_awl": total_fixed
        }

    def calculate_from_text(self, text: str) -> str:
        """الدالة الرئيسية التي يستدعيها الـ Agent"""
        heirs = self.parse_heirs(text)
        if not heirs:
            return "لم أستطع فهم الورثة في النص. جرب صيغة مثل: 'زوجة و3 أولاد وبنت وأم وأب'"

        result = self.calculate(heirs)

        explanation = f"**نتيجة حساب التركة**\n\n{text}\n\n"

        if result["awl_applied"]:
            explanation += "⚠️ **تم تطبيق العول** (التركة مش كفاية)\n\n"

        explanation += "**توزيع الميراث:**\n"
        for h in result["heirs"]:
            percentage = float(h["share"]) * 100
            explanation += f"• {h['name']} ({h['count']}): {h['share']} ≈ {percentage:.2f}%\n"

        explanation += "\n" + self.explain_awl()
        return explanation

    def explain_awl(self) -> str:
        return """
**العول** يعني: الفلوس اللي سابها المتوفى **مش كفاية** للنسب المستحقة.
فبنقلل نسبة كل واحد شوية عشان الكل ياخد حاجة.
مثال: زوجة + أم + أب → غالباً بيحصل فيه عول.
"""

if __name__ == "__main__":
    calc = FaraidCalculator()
    print(calc.calculate_from_text("زوجة و3 أولاد وبنت وأم وأب"))