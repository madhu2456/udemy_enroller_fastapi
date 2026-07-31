"""Unique AEO answer-block copy for coupon detail pages (Fix 33)."""

from app.core.coupon_content import build_coupon_answer_block


class TestBuildCouponAnswerBlock:
    def test_lead_contains_title_and_code(self):
        course = {
            "title": "Python for Beginners",
            "category": "Development",
            "language": "English",
            "coupon_code": "FREEPY2024",
            "rating": 4.6,
            "price": 2499,
            "last_checked_at": "2026-07-30T12:00:00",
        }
        block = build_coupon_answer_block(course, "Development")
        assert "Python for Beginners" in block["lead"]
        assert "FREEPY2024" in block["lead"]
        assert "Development" in block["lead"]
        assert "English" in block["lead"]
        assert "4.6" in block["lead"]
        assert "2499" in block["lead"]
        assert "2026-07-30" in block["lead"]
        assert "not affiliated" in block["lead"].lower()
        assert "Python for Beginners" in block["answer_heading"]

    def test_faqs_length_three(self):
        course = {
            "title": "Excel Masterclass",
            "coupon_code": "XL100",
        }
        block = build_coupon_answer_block(course, "Office Productivity")
        assert len(block["faqs"]) == 3
        for faq in block["faqs"]:
            assert faq["question"]
            assert faq["answer"]
        assert any("guaranteed" in f["question"].lower() for f in block["faqs"])
        assert any("enroll" in f["question"].lower() for f in block["faqs"])
        assert any("publishes" in f["question"].lower() for f in block["faqs"])

    def test_handles_missing_optional_fields(self):
        course = {"title": "Minimal Course", "coupon_code": "MIN1"}
        block = build_coupon_answer_block(course, "")
        assert "Minimal Course" in block["lead"]
        assert "MIN1" in block["lead"]
        # No invented rating/price when missing
        assert "Source rating" not in block["lead"]
        assert "List price" not in block["lead"]
        assert "Last checked by Udemy Enroller on" not in block["lead"]
        fact_text = " ".join(block["facts"])
        assert "Language:" not in fact_text
        assert "Last checked:" not in fact_text
        assert "Coupon code: MIN1" in fact_text
        assert any("not affiliated" in f.lower() for f in block["facts"])

    def test_empty_course_fallbacks(self):
        block = build_coupon_answer_block({}, "General")
        assert "this Udemy course" in block["lead"]
        assert "this Udemy course" in block["answer_heading"]
        assert len(block["faqs"]) == 3
        assert block["facts"][0].startswith("Course:")
        assert "Category: General" in block["facts"]

    def test_invalid_rating_and_price_ignored(self):
        course = {
            "title": "Odd Data",
            "coupon_code": "ODD",
            "rating": "n/a",
            "price": "free",
        }
        block = build_coupon_answer_block(course, "Other")
        assert "Source rating" not in block["lead"]
        assert "List price" not in block["lead"]
        assert "ODD" in block["lead"]

    def test_empty_coupon_code_lead_is_grammatical(self):
        block = build_coupon_answer_block({"title": "No Code Course"}, "Dev")
        assert "Use code  " not in block["lead"]
        assert "Use the coupon on this page" in block["lead"]

    def test_empty_coupon_code_enroll_faq_branch(self):
        block = build_coupon_answer_block({"title": "No Code Course"}, "Dev")
        enroll = next(f for f in block["faqs"] if "enroll" in f["question"].lower())
        assert enroll["answer"].startswith("Open the course on Udemy via the link")
        assert "Copy the coupon code" not in enroll["answer"]

    def test_empty_coupon_code_guaranteed_faq_branch(self):
        block = build_coupon_answer_block({"title": "No Code Course"}, "Dev")
        guaranteed = next(
            f for f in block["faqs"] if "guaranteed" in f["question"].lower()
        )
        guaranteed_answer = guaranteed["answer"]
        assert "This free offer may expire" in guaranteed_answer
        assert "The code on this page" not in guaranteed_answer
