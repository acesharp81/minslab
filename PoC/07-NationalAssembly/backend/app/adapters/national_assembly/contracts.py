from __future__ import annotations

from dataclasses import dataclass


OPEN_API_BASE_URL = "https://open.assembly.go.kr/portal/openapi"
CONTRACT_VERIFIED_AT = "2026-08-12"


@dataclass(frozen=True, slots=True)
class SourceContract:
    source_key: str
    resource: str
    portal_inf_id: str
    portal_inf_seq: int
    required_parameters: tuple[str, ...]
    columns: tuple[str, ...]
    verified_at: str = CONTRACT_VERIFIED_AT


CONTRACTS: dict[str, SourceContract] = {
    item.source_key: item
    for item in (
        SourceContract(
            "assembly_schedule", "ALLSCHEDULE", "OOWY4R001216HX11437", 2, (),
            ("SCH_KIND", "SCH_CN", "SCH_DT", "SCH_TM", "CONF_DIV", "CMIT_NM",
             "CONF_SESS", "CONF_DGR", "EV_INST_NM", "EV_PLC"),
        ),
        SourceContract(
            "members", "ALLNAMEMBER", "OOWY4R001216HX11439", 2, (),
            ("NAAS_CD", "NAAS_NM", "NAAS_CH_NM", "NAAS_EN_NM", "BIRDY_DIV_CD",
             "BIRDY_DT", "DTY_NM", "PLPT_NM", "ELECD_NM", "ELECD_DIV_NM",
             "CMIT_NM", "BLNG_CMIT_NM", "RLCT_DIV_NM", "GTELT_ERACO", "NTR_DIV",
             "NAAS_TEL_NO", "NAAS_EMAIL_ADDR", "NAAS_HP_URL", "AIDE_NM",
             "CHF_SCRT_NM", "SCRT_NM", "BRF_HST", "OFFM_RNUM_NO", "NAAS_PIC"),
        ),
        SourceContract(
            "bills", "ALLBILLV2", "OOWY4R001216HX11536", 1, ("ERACO",),
            ("ERACO", "BILL_ID", "BILL_NO", "BILL_KND", "BILL_NM", "PPSR_KND",
             "PPSR_NM", "PPSL_SESS", "PPSL_DT", "JRCMIT_NM", "JRCMIT_CMMT_DT",
             "JRCMIT_PRSNT_DT", "JRCMIT_PROC_DT", "JRCMIT_PROC_RSLT",
             "LAW_CMMT_DT", "LAW_PRSNT_DT", "LAW_PROC_DT", "LAW_PROC_RSLT",
             "RGS_PRSNT_DT", "RGS_RSLN_DT", "RGS_CONF_NM", "RGS_CONF_RSLT",
             "GVRN_TRSF_DT", "PROM_LAW_NM", "PROM_DT", "PROM_NO", "LINK_URL",
             "PASSGUBN", "PROC_STAGE_CD", "HWP_URL1", "HWP_URL2", "PDF_URL1", "PDF_URL2"),
        ),
        SourceContract(
            "plenary_minutes", "nzbyfwhwaoanttzje", "OO1X9P001017YF13038", 2,
            ("DAE_NUM", "CONF_DATE"),
            ("CONFER_NUM", "TITLE", "CLASS_NAME", "DAE_NUM", "CONF_DATE", "SUB_NAME",
             "VOD_LINK_URL", "CONF_LINK_URL", "PDF_LINK_URL", "CONF_ID"),
        ),
        SourceContract(
            "committee_minutes", "ncwgseseafwbuheph", "OR137O001023MZ19321", 2,
            ("DAE_NUM", "CONF_DATE"),
            ("CONFER_NUM", "TITLE", "CLASS_NAME", "DAE_NUM", "COMM_NAME",
             "VODCOMM_CODE", "CONF_DATE", "SUB_NAME", "VOD_LINK_URL", "CONF_LINK_URL",
             "PDF_LINK_URL", "PDF_FILE_ID", "DEPT_CD", "CONF_ID"),
        ),
        SourceContract(
            "meeting_agendas", "VCONFBILLLIST", "OOWY4R001216HX11525", 2, (),
            ("CONF_ID", "ERACO", "SESS", "DGR", "BILL_ID", "BILL_NM", "LINK_URL"),
        ),
        SourceContract(
            "plenary_votes", "nojepdqqaweusdfbi", "OPR1MQ000998LC12535", 2,
            ("AGE", "BILL_ID"),
            ("HG_NM", "HJ_NM", "POLY_NM", "ORIG_NM", "MEMBER_NO", "POLY_CD",
             "ORIG_CD", "VOTE_DATE", "BILL_NO", "BILL_NAME", "BILL_ID", "LAW_TITLE",
             "CURR_COMMITTEE", "RESULT_VOTE_MOD", "DEPT_CD", "CURR_COMMITTEE_ID",
             "DISP_ORDER", "BILL_URL", "BILL_NAME_URL", "SESSION_CD", "CURRENTS_CD",
             "AGE", "MONA_CD"),
        ),
        SourceContract(
            "committees", "nxrvzonlafugpqjuh", "O2Q4ZT001004PV11014", 2, (),
            ("CMT_DIV_CD", "CMT_DIV_NM", "HR_DEPT_CD", "COMMITTEE_NAME", "HG_NM",
             "HG_NM_LIST", "LIMIT_CNT", "CURR_CNT", "POLY99_CNT", "POLY_CNT"),
        ),
    )
}


def get_contract(source_key: str) -> SourceContract:
    try:
        return CONTRACTS[source_key]
    except KeyError as error:
        raise KeyError(f"unverified source contract: {source_key}") from error
