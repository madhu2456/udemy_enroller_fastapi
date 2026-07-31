"""Unique extractable copy for public coupon detail pages (AEO/thin-content defense)."""


def build_coupon_answer_block(course: dict, category_name: str) -> dict:
    """Return heading, lead (~40–70 words when optional fields present), facts, faqs."""
    title = (course.get("title") or "this Udemy course").strip()
    cat = (category_name or course.get("category") or "General").strip()
    lang = (course.get("language") or "").strip()
    code = (course.get("coupon_code") or "").strip()
    rating = course.get("rating")
    last = (course.get("last_checked_at") or "")[:10] if course.get("last_checked_at") else ""
    price = course.get("price")

    lang_bit = f" in {lang}" if lang else ""
    price_bit = ""
    try:
        if price is not None and float(price) > 0:
            price_bit = f" List price in source data was about ₹{int(float(price))} before the coupon."
    except (TypeError, ValueError):
        pass

    rating_bit = ""
    try:
        if rating is not None and float(rating) > 0:
            rating_bit = f" Source rating: {float(rating):.1f}/5."
    except (TypeError, ValueError):
        pass

    checked_bit = f" Last checked by Udemy Enroller on {last}." if last else ""

    if code:
        code_bit = f" Use code {code} at Udemy checkout if the offer is still active."
    else:
        code_bit = " Use the coupon on this page at Udemy checkout if the offer is still active."

    lead = (
        f"“{title}” is listed with a free (100% off) Udemy promotional coupon"
        f" in the {cat} category{lang_bit}."
        f"{code_bit}"
        f"{price_bit}{rating_bit}{checked_bit}"
        f" Udemy Enroller is not affiliated with Udemy; validity can change."
    )

    facts = [
        f"Course: {title}",
        f"Category: {cat}",
    ]
    if lang:
        facts.append(f"Language: {lang}")
    if code:
        facts.append(f"Coupon code: {code}")
    if last:
        facts.append(f"Last checked: {last}")
    facts.append("Affiliation: Independent listing — not affiliated with Udemy, Inc.")

    if code:
        enroll_answer = (
            f"Copy the coupon code {code}, open the course on Udemy, apply it at checkout, "
            f"and confirm the price shows free (or the expected discount). "
            f"You need a Udemy account. If the code fails, browse other {cat} free coupons."
        )
    else:
        enroll_answer = (
            f"Open the course on Udemy via the link on this page, apply any listed coupon at checkout, "
            f"and confirm the price shows free (or the expected discount). "
            f"You need a Udemy account. If the code fails, browse other {cat} free coupons."
        )

    faqs = [
        {
            "question": f"Is the free coupon for {title} guaranteed?",
            "answer": (
                (
                    f"No. The code {code} may expire or stop applying at any time. "
                    if code
                    else "No. This free offer may expire or stop applying at any time. "
                )
                + "Always confirm the cart total on Udemy before enrolling. "
                + "This listing is maintained by Udemy Enroller for discovery only."
            ),
        },
        {
            "question": f"How do I enroll in {title} for free?",
            "answer": enroll_answer,
        },
        {
            "question": "Who publishes this coupon page?",
            "answer": (
                "Udemy Enroller by Madhu Dadi — an open-source helper for finding free Udemy coupons "
                "and optionally attempting enrollment when you start a run. "
                "It is not affiliated with, endorsed by, or partnered with Udemy."
            ),
        },
    ]

    return {
        "answer_heading": f"What is the free coupon for {title}?",
        "lead": lead,
        "facts": facts,
        "faqs": faqs,
    }
