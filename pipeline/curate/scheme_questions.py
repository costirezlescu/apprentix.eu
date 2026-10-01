"""The standard questionnaire behind every Cedefop apprenticeship scheme fiche.

Each fiche answers the same 40 questions. 32 are multiple choice: the fiche
marks the selected option(s). Here each of those becomes a record field with
short, readable option labels, listed in Cedefop's own option order.

"multi" questions allow several answers and are stored as lists.
`options` are Cedefop's option texts (upper-case, as published) mapped to our
short labels; the merge script fails loudly if a fiche shows an option that is
not listed here, so a changed questionnaire is never silently mis-mapped.
"""

QUESTIONS = {
    1: ("q_introduced", "Introduced", False, {
        "LONG HISTORY (BEFORE 2000)": "Before 2000",
        "RECENTLY INTRODUCED (BETWEEN 2000-2012)": "2000–2012",
        "NEW PATHWAY (AFTER 2012)": "After 2012"}),
    2: ("q_origin", "Origin", True, {
        "TRADITIONAL CRAFTSMANSHIP (MASTER-APPRENTICE RELATION) TO PREPARE APPRENTICES FOR THE OCCUPATION": "Craft tradition",
        "SCHOOL-BASED VET TRACK BY INCLUDING MORE WORK-BASED LEARNING TO SUPPLY SKILLED WORKFORCE TO MATCH LABOUR MARKET NEEDS": "Grew out of school-based VET",
        "EX-NOVO": "Created from scratch",
        "OTHER": "Other"}),
    3: ("q_age_limits", "Age limits in law", False, {
        "MINIMUM AND MAXIMUM AGE LIMITS DEFINED": "Minimum and maximum",
        "MINIMUM AGE LIMITS DEFINED ONLY": "Minimum only",
        "OTHER": "Other"}),
    4: ("q_typical_age", "Typical learner age", True, {
        "BETWEEN 15 AND 18": "15–18",
        "BETWEEN 18 AND 24": "18–24",
        "ABOVE 24": "Over 24"}),
    6: ("q_share_of_vet", "Share of VET learners", False, {
        "MORE THAN 60% OF VET LEARNERS": "Over 60%",
        "BETWEEN 30%-60% OF VET LEARNERS": "30–60%",
        "BETWEEN 10% AND 30% OF VET LEARNERS": "10–30%",
        "LESS THAN 10% OF VET LEARNERS": "Under 10%"}),
    7: ("q_in_nqf", "In the national qualifications framework", False, {
        "YES": "Yes", "NO": "No", "THERE IS NO NQF": "No NQF"}),
    8: ("q_in_isced", "In the ISCED 2011 mapping", False, {"YES": "Yes", "NO": "No"}),
    9: ("q_qualification_route", "Same qualification via other routes", False, {
        "QUALIFICATIONS CAN ONLY BE OBTAINED THROUGH THIS APPRENTICESHIP SCHEME": "Only through apprenticeship",
        "THE SAME QUALIFICATIONS CAN BE ACHIEVED ALSO THROUGH OTHER SCHEMES (I.E. SCHOOL-BASED VET)": "Also through school-based VET"}),
    10: ("q_qualification_type", "Type of qualification", True, {
        "FORMAL VET QUALIFICATION (WHICH DOES NOT INDICATE THE PATHWAY)": "VET qualification, route not shown",
        "FORMAL VET QUALIFICATION (WHICH INDICATES THE PATHWAY)": "VET qualification, route shown",
        "FORMAL APPRENTICESHIP QUALIFICATION (JOURNEYMAN, ETC.)": "Apprenticeship qualification (journeyman etc.)",
        "OTHERS": "Other"}),
    11: ("q_access_to_he", "Direct access to higher education", False, {"YES": "Yes", "NO": "No"}),
    13: ("q_national_coordination", "National coordinating body", False, {"YES": "Yes", "NO": "No"}),
    14: ("q_partners_design", "Social partners shape content", True, {
        "ROLE IN DESIGNING QUALIFICATION": "Design qualifications",
        "ROLE IN DESIGNING CURRICULA": "Design curricula",
        "OTHER": "Other",
        "NO ROLE": "No role"}),
    15: ("q_partners_implement", "Social partners in implementation", True, {
        "ROLE IN FINAL ASSESSMENT OF APPRENTICES": "Final assessment",
        "ROLE IN ACCREDITATION OF COMPANIES": "Accredit companies",
        "ROLE IN MONITORING OF THE IN-COMPANY TRAINING": "Monitor in-company training",
        "OTHER": "Other",
        "NO ROLE": "No role"}),
    18: ("q_quality_assurance", "Quality assurance", True, {
        "YES, STRUCTURED MONITORING PROCESSES DURING THE APPRENTICESHIP": "Monitoring during training",
        "YES, OUTPUT EVALUATION WHEN APPRENTICESHIP IS COMPLETED": "Evaluation at completion",
        "YES, GRADUATE TRACKING": "Graduate tracking",
        "YES, IMPACT EVALUATION OR COST-BENEFIT ANALYSES": "Impact or cost–benefit evaluation",
        "OTHER": "Other"}),
    19: ("q_alternation_compulsory", "Alternation school/company compulsory", False, {"YES": "Yes", "NO": "No"}),
    20: ("q_min_workplace_share", "Minimum workplace share", False, {
        "YES, EQUIVALENT OR MORE THAN 50% OF SCHEME DURATION": "50% or more",
        "YES, BETWEEN 20% AND 50% OF THE SCHEME DURATION": "20–50%",
        "YES, LESS THAN 20% OF THE SCHEME DURATION": "Under 20%",
        "NO, NO MINIMUM SHARE IS COMPULSORY": "No minimum"}),
    21: ("q_training_vs_work_time", "Training time distinguished from work time", False, {
        "YES, THE LEGAL FRAMEWORK MAKES THIS DISTINCTION": "Yes",
        "NO, THE LEGAL FRAMEWORK MAKES NO DISTINCTION": "No"}),
    22: ("q_alternation_form", "Form of alternation", True, {
        "EVERY WEEK INCLUDES BOTH VENUES": "Every week, both venues",
        "ONE OR MORE WEEKS (LESS THAN 1 MONTH) SPENT AT SCHOOL FOLLOWED BY ONE OR MORE WEEKS AT WORKPLACE": "Blocks of weeks",
        "ONE OR MORE MONTHS (LESS THAN 1 YEAR) SPENT AT SCHOOL FOLLOWED BY ONE OR MORE MONTHS AT WORKPLACE": "Blocks of months",
        "A LONGER PERIOD (1-2 YEARS) SPENT AT SCHOOL FOLLOWED BY A LONGER PERIOD SPENT TRAINING AT WORKPLACE": "School years, then workplace",
        "VARIOUS – DEPENDS ON AGREEMENTS BETWEEN THE SCHOOL AND THE COMPANY": "Varies by agreement",
        "OTHER": "Other",
        "NOT SPECIFIED": "Not specified"}),
    23: ("q_training_basis", "Basis of training", True, {
        "THE SCHEME IS IMPLEMENTED VIA A SPECIFIC APPRENTICESHIP PROGRAMME": "Own apprenticeship programme",
        "THE SCHEME IS IMPLEMENTED ON THE BASIS OF THE SCHOOL-BASED VET PROGRAMME": "School-based VET programme",
        "THE SCHEME IS IMPLEMENTED BASED ON THE VET STANDARDS (VALID GENERALLY FOR ALL VET SCHEMES)": "General VET standards",
        "OTHER": "Other"}),
    25: ("q_training_plan", "Workplace training plan required", False, {
        "YES, THE TRAINING PLAN IS BASED ON THE NATIONAL/SECTORAL REQUIREMENTS FOR THE IN-COMPANY TRAINING": "Yes, national/sectoral",
        "YES, THE TRAINING PLAN IS AGREED AT THE LEVEL OF SCHOOL AND COMPANY": "Yes, agreed by school and company",
        "NO, IS NOT REQUIRED FORMALLY": "No"}),
    26: ("q_company_requirements", "Requirements on companies", True, {
        "HAVE TO PROVIDE A SUITABLE LEARNING ENVIRONMENT": "Suitable learning environment",
        "HAVE TO PROVIDE A MENTOR / TUTOR / TRAINER": "Mentor or trainer",
        "OTHER": "Other"}),
    28: ("q_sanctions", "Sanctions on companies not training", False, {"YES": "Yes", "NO": "No"}),
    29: ("q_learner_status", "Learner status", True, {
        "ONLY STUDENT": "Student",
        "ONLY EMPLOYEE": "Employee",
        "APPRENTICE IS A SPECIFIC STATUS (STUDENT AND EMPLOYEE COMBINED)": "Specific apprentice status",
        "OTHER": "Other"}),
    30: ("q_written_arrangement", "Written arrangement required", False, {"YES": "Yes", "NO": "No"}),
    31: ("q_contract_type", "Type of arrangement", True, {
        "APPRENTICESHIPS ARE AN ORDINARY EMPLOYMENT CONTRACT": "Ordinary employment contract",
        "APPRENTICESHIPS ARE A SPECIFIC TYPE OF CONTRACT": "Specific apprenticeship contract",
        "ANOTHER TYPE OF FORMAL AGREEMENT, NOT A CONTRACT": "Formal agreement, not a contract"}),
    32: ("q_contract_registered", "Arrangement registered at", True, {
        "AT THE SCHOOL": "School",
        "AT THE MINISTRY OF EMPLOYMENT": "Employment ministry",
        "AT THE CHAMBERS": "Chambers",
        "AT THE MINISTRY OF EDUCATION": "Education ministry",
        "OTHER": "Other"}),
    33: ("q_compensation", "Pay", True, {
        "YES, ALL APPRENTICES RECEIVE A WAGE (TAXABLE INCOME)": "Wage",
        "YES, ALL APPRENTICES RECEIVE AN ALLOWANCE (NOT A FORM OF TAXABLE INCOME)": "Allowance",
        "APPRENTICES RECEIVE A REIMBURSEMENT OF EXPENSES": "Expenses only",
        "NO FORM OF COMPENSATION IS FORESEEN BY LAW": "None required by law"}),
    34: ("q_wage_setting", "How pay is set", True, {
        "BY LAW (APPLYING FOR ALL)": "By law",
        "BY CROSS-SECTORAL COLLECTIVE AGREEMENTS AT NATIONAL OR LOCAL LEVEL": "Cross-sector agreements",
        "BY SECTORAL COLLECTIVE AGREEMENTS AT NATIONAL OR LOCAL LEVEL": "Sectoral agreements",
        "BY FIRM-LEVEL COLLECTIVE AGREEMENTS OR INDIVIDUAL AGREEMENTS BETWEEN APPRENTICE AND COMPANY": "Firm or individual agreements",
        "OTHER": "Other"}),
    35: ("q_pay_funded_by", "Pay funded by", True, {
        "EMPLOYERS": "Employers", "STATE": "State", "OTHER": "Other"}),
    36: ("q_training_cost_funding", "In-company training costs funded by", True, {
        "SINGLE EMPLOYERS HOSTING APPRENTICES": "Host employers",
        "TRAINING FUNDS": "Training funds",
        "STATE": "State",
        "OTHER": "Other"}),
    37: ("q_financial_incentives", "Financial incentives for companies", True, {
        "YES, SUBSIDIES": "Subsidies",
        "YES, TAX DEDUCTIONS": "Tax deductions",
        "YES, OTHER INCENTIVES": "Other",
        "NO FINANCIAL INCENTIVES": "None"}),
    38: ("q_nonfinancial_incentives", "Non-financial support for companies", True, {
        "SYSTEMATIC CAMPAIGNS TO ATTRACT EMPLOYERS": "Campaigns",
        "ONLINE PLATFORMS TO POST PLACEMENTS/RECRUIT APPRENTICES": "Online platforms",
        "SUPPORT BY CHAMBERS OR INTERMEDIARY BODIES TO JOIN OR DELIVER TRAINING": "Chamber or intermediary support",
        "GUIDELINES FOR DAY-TO-DAY COLLABORATION WITH SCHOOLS": "School collaboration guidelines",
        "SUPPORT FOR TRAINING IN-COMPANY TRAINERS": "Trainer training",
        "OTHER": "Other"}),
    39: ("q_pay_covers_school", "Pay covers school time", False, {
        "YES": "Yes",
        "NO, IT COVERS ONLY THE TIME SPENT IN THE COMPANY": "No, company time only"}),
    40: ("q_learner_incentives", "Incentives for learners", True, {
        "YES, GRANTS PAID TO LEARNERS TO TOP UP THEIR REMUNERATION": "Pay top-up grants",
        "YES, GRANTS PAID TO LEARNERS RELATED TO OTHER COSTS (TRAVEL, FOOD ETC.)": "Grants for other costs",
        "YES, RECOGNITION OF PRIOR LEARNING / FAST-TRACK OPPORTUNITIES": "Recognition of prior learning",
        "YES, GUIDANCE OR LEARNER SUPPORT": "Guidance",
        "YES, OTHER TYPES OF INCENTIVES": "Other",
        "NO": "None"}),
}

# Free-text answers kept (short) for display and verification.
TEXT_QUESTIONS = {5: ("q_learners_text", "Learners (as stated)"), 12: ("q_duration_text", "Duration (as stated)")}

SECTIONS = [
    ("History and learners", [1, 2, 3, 4, 6]),
    ("Qualification", [7, 8, 9, 10, 11]),
    ("Governance", [13, 14, 15, 18]),
    ("Training at the workplace", [19, 20, 21, 22, 23, 25, 26, 28]),
    ("Contract and pay", [29, 30, 31, 32, 33, 34, 39]),
    ("Financing and incentives", [35, 36, 37, 38, 40]),
]
