"""Arithmetic replay, never a retrospective strategy recommendation or a cash claim."""

from decimal import Decimal

from local_market_agent.horse_racing.models import HistoricalRecord, OfficialMeeting


def amount(value):
    return None if value is None else float(value.quantize(Decimal("0.01")))


def curve_metrics(initial, rows, key):
    balance, peak = initial, initial
    points = [{"race_no": 0, "balance": amount(initial)}]
    max_loss = Decimal(0)
    max_fraction = Decimal(0)
    for row in rows:
        if row[key] is None or row["participation"] == "UNKNOWN":
            return {
                "status": "UNKNOWN",
                "balance": None,
                "gross_return": None,
                "net_profit": None,
                "roi": None,
                "bankroll_return": None,
                "curve": points,
                "max_drawdown": None,
                "max_drawdown_fraction": None,
            }
        balance += Decimal(str(row[key])) - Decimal(str(row["stake"]))
        peak = max(peak, balance)
        max_loss = max(max_loss, peak - balance)
        max_fraction = max(max_fraction, (peak - balance) / peak)
        points.append({"race_no": row["race_no"], "balance": amount(balance)})
    stake = sum(Decimal(str(r["stake"])) for r in rows)
    profit = balance - initial
    return {
        "status": "complete_arithmetic_only",
        "balance": amount(balance),
        "gross_return": amount(stake + profit),
        "net_profit": amount(profit),
        "roi": float(profit / stake) if stake else None,
        "bankroll_return": float(profit / initial),
        "curve": points,
        "max_drawdown": amount(max_loss),
        "max_drawdown_fraction": float(max_fraction),
        "drawdown_basis": "race-close entitlement balance; not intrarace or redeemed cash",
    }


def replay_history(record: HistoricalRecord, official: OfficialMeeting | None = None):
    if official and (
        official.meeting_date != record.meeting_date or official.course != record.course
    ):
        raise ValueError("Official meeting does not match the historical record")
    results = {r.race_no: r for r in official.races} if official else {}
    if official and len(results) != len(official.races):
        raise ValueError("Duplicate official race")
    if official and set(results) != {r.race_no for r in record.races}:
        raise ValueError("Historical record must explicitly cover every official meeting race")
    rows = []
    pools = {
        p: {
            "tickets": 0,
            "known_outcomes": 0,
            "wins": 0,
            "stake": Decimal(0),
            "official_gross_return": Decimal(0),
        }
        for p in ("WIN", "PLACE")
    }
    tickets = []
    for race in record.races:
        result = results.get(race.race_no)
        stake = sum((t.stake for t in race.tickets), Decimal(0))
        settled = result is not None and result.supported
        known = settled and all(
            t.horse_no in {r.horse_no for r in result.runners} and t.stake % result.unit_bet == 0
            for t in race.tickets
        )
        gross = Decimal(0) if race.participation == "NOT_PLACED" else None
        if race.participation == "REPORTED_TICKETS" and known:
            gross = Decimal(0)
        row_tickets = []
        for ticket in race.tickets:
            payout = None
            outcome = "UNKNOWN"
            if known:
                rate = result.dividends[ticket.pool].get(str(ticket.horse_no))
                outcome = "won" if rate is not None else "lost"
                payout = (
                    (ticket.stake * rate / result.unit_bet).quantize(Decimal("0.01"))
                    if rate is not None
                    else Decimal(0)
                )
                gross += payout
            pool = pools[ticket.pool]
            pool["tickets"] += 1
            pool["stake"] += ticket.stake
            if payout is not None:
                pool["known_outcomes"] += 1
                pool["wins"] += outcome == "won"
                pool["official_gross_return"] += payout
            entry = {
                **ticket.model_dump(mode="json"),
                "race_no": race.race_no,
                "official_outcome": outcome,
                "official_entitlement": amount(payout),
                "reported_outcome_agrees": None
                if ticket.reported_outcome == "UNKNOWN" or outcome == "UNKNOWN"
                else ticket.reported_outcome == outcome,
                "original_prediction": "UNKNOWN",
                "pre_race_value": "UNKNOWN",
                "cash_redemption": "UNKNOWN",
            }
            tickets.append(entry)
            row_tickets.append(entry)
        top3 = (
            [
                r.horse_no
                for r in sorted(result.runners, key=lambda r: int(r.placing))
                if r.placing in {"1", "2", "3"}
            ]
            if settled
            else None
        )
        rows.append(
            {
                "race_no": race.race_no,
                "participation": race.participation,
                "ticket_count": len(race.tickets),
                "stake": amount(stake),
                "provisional_gross_return": amount(race.provisional_gross_return)
                if race.participation != "NOT_PLACED"
                else 0,
                "official_gross_return": amount(gross),
                "official_net_profit": amount(gross - stake) if gross is not None else None,
                "redeemed_cash": amount(race.redeemed_cash),
                "redemption_evidence": race.redemption_evidence,
                "official_top3": top3,
                "reported_top3": race.reported_top3,
                "top3_agrees": None
                if top3 is None or race.reported_top3 is None
                else top3 == race.reported_top3,
                "payout_agrees": None
                if gross is None or race.provisional_gross_return is None
                else gross == race.provisional_gross_return,
                "source_url": result.source_url if result else None,
                "tickets": row_tickets,
                "historical_recommendation": "UNKNOWN",
                "historical_no_bet_recommendation": "UNKNOWN",
            }
        )
    total_stake = sum((t.stake for r in record.races for t in r.tickets), Decimal(0))
    total_n = len(tickets)
    total_known = sum(p["known_outcomes"] for p in pools.values())
    wins = sum(p["wins"] for p in pools.values())
    for pool in pools.values():
        pool["hit_rate"] = pool["wins"] / pool["known_outcomes"] if pool["known_outcomes"] else None
        pool["official_gross_return"] = (
            amount(pool["official_gross_return"])
            if pool["known_outcomes"] == pool["tickets"]
            else None
        )
        pool["stake"] = amount(pool["stake"])
    cash_known = all(
        r.redeemed_cash is not None for r in record.races if r.participation != "NOT_PLACED"
    ) and all(r.participation != "UNKNOWN" for r in record.races)
    cash_balance = (
        record.initial_bankroll
        - total_stake
        + sum((r.redeemed_cash or Decimal(0) for r in record.races), Decimal(0))
        if cash_known
        else None
    )
    return {
        "schema_version": 1,
        "kind": "historical_racing_replay",
        "meeting_date": record.meeting_date.isoformat(),
        "course": record.course,
        "currency": "HKD",
        "record_provenance": record.provenance,
        "initial_bankroll": amount(record.initial_bankroll),
        "race_count": len(rows),
        "bet_races": sum(bool(r.tickets) for r in record.races),
        "ticket_count": total_n,
        "known_outcomes": total_known,
        "wins": wins if total_known == total_n else None,
        "hit_rate": wins / total_n if total_known == total_n and total_n else None,
        "total_stake": amount(total_stake),
        "pools": pools,
        "races": rows,
        "provisional": curve_metrics(record.initial_bankroll, rows, "provisional_gross_return"),
        "official_entitlement": curve_metrics(
            record.initial_bankroll, rows, "official_gross_return"
        ),
        "cash": {
            "status": "document_referenced_user_record" if cash_known else "UNKNOWN",
            "redeemed_balance": amount(cash_balance),
            "verified_by_operator": False,
        },
        "risk": {
            "fixed_unit_stakes": all(
                t.stake == record.unit_stake for r in record.races for t in r.tickets
            ),
            "precommitted_meeting_budget": amount(record.precommitted_meeting_budget),
            "budget_adherence": "UNKNOWN"
            if record.precommitted_meeting_budget is None
            else (
                "within_recorded_cap"
                if total_stake <= record.precommitted_meeting_budget
                else "exceeded"
            ),
            "all_reported_stakes_affordable_without_recycling_returns": total_stake
            <= record.initial_bankroll,
            "chasing_losses_or_wins": "UNKNOWN: fixed recorded stakes alone do not prove historical intent",
        },
        "calibration": {
            "status": "UNKNOWN",
            "win_brier": None,
            "place_brier": None,
            "reason": "No verified original pre-race probability series supplied to historical ticket replay",
        },
        "strategy_backtest": {
            "eligible": False,
            "status": "UNKNOWN",
            "reason": "Ticket/outcome replay does not establish original point-in-time predictions or odds",
        },
        "limitations": [
            "Reported actual tickets are not independently verified betting receipts.",
            "Official dividends establish rule-based entitlement, not redeemed cash.",
            "Unbet races are not losses or reconstructed NO BET recommendations.",
            "One meeting and correlated tickets cannot establish a stable profitable strategy.",
            "Race-close drawdown is not intrarace cash drawdown; actual timing is unknown.",
        ],
    }
