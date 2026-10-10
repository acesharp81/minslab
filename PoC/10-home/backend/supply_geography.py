"""Reviewed administrative membership and independent milestone evidence."""
from .roadmap import source_events


def municipal_membership(rows,boundaries,districts,key_for):
    resolved={}
    def explicit(row):
        matches=[area["id"] for area in boundaries if area["region"]==row["region"] and row.get("municipality") in
                 {area["name"],area["name"][:-1] if area["region"]=="경기도" else area["name"]}]
        return matches[0] if len(matches)==1 else None
    for row in rows:
        area=explicit(row)
        if area:resolved[row["id"]]=area
    for row in rows:
        if row["id"] in resolved:continue
        key=key_for(row)
        peers={explicit(peer) for peer in rows if key and key_for(peer)==key and explicit(peer)}
        if len(peers)==1:
            resolved[row["id"]]=peers.pop()
            continue
        names={district["name"] for district in districts if row["id"] in district["project_ids"]}
        areas={area["id"] for area in boundaries if area["region"]==row["region"] and names.intersection(area.get("district_names",[]))}
        if len(areas)==1:resolved[row["id"]]=areas.pop()
    return resolved


def block_milestones(rows,links,reference):
    contracts=[row for row in rows if row["source_id"] in {"lh_construction","lh_progress"} and "MULTI_SITE_CONTRACT" not in row.get("warnings",[])]
    contract=contracts[0] if len(contracts)==1 else None
    notices=[links[row["id"]] for row in rows if row["id"] in links]
    notice=notices[0] if len(notices)==1 else None
    events=[event for row in rows for event in source_events(row,reference)]
    def stage(key,label,actual=None,reported=False):
        plans=[event for event in events if event["stage"]==key]
        return {"stage":key,"label":label,"status":"REPORTED" if reported else "OBSERVED" if actual else "PLANNED" if plans else "UNKNOWN",
                "actual_date":actual,"planned_month":min((event["month"] for event in plans),default=None),
                "evidence_url":notice.get("evidence_url") if key=="SUPPLY" and notice else contract.get("evidence_url") if contract else None}
    result=[stage("APPROVAL","인허가"),stage("CONSTRUCTION","착공",contract.get("start_actual_date") if contract else None),
            stage("COMPLETION","준공",reported=bool(contract and contract.get("stage")=="COMPLETED")),
            stage("SUPPLY","분양·모집",notice.get("source_date") if notice else None),stage("MOVE_IN","입주")]
    result[1].update(progress_pct=contract.get("progress_pct") if contract else None,report_date=(contract.get('progress_date') or contract.get("base_date")) if contract else None)
    result[2].update(report_date=contract.get("base_date") if contract else None)
    return result
