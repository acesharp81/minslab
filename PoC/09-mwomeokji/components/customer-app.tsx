"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Heart, MessageCircleMore, Minus, Plus, Send, ShoppingBag, X } from "lucide-react";
import { api, money } from "../lib/client";
import { ALLERGENS, DIET_RULES, emptyProfile, type MenuItemData, type PreferenceProfile, type Recommendation } from "../lib/types";
import type { DialogueState, VisitMode } from "../lib/dialogue";

type CartLine = { id: string; name: string; emoji: string; quantity: number; lineTotal: number; assignedTo?: string; optionNames: string[]; safety: { allowed: boolean; reasons: string[] } };
type Cart = { items: CartLine[]; total: number; canOrder: boolean };
type Bootstrap = { store: { name: string; description: string }; menu: MenuItemData[]; profile: PreferenceProfile; cart: Cart; visitMode: VisitMode | null; dialogue: DialogueState };
type Order = { id: string; code: string; status: string; total: number; createdAt: string; fulfillmentType: VisitMode; lines: { id: string; menuName: string; quantity: number; lineTotal: number }[] };
type ChatLine = { role: "user" | "assistant"; text: string; recommendations?: Recommendation[]; confirmCheckout?: boolean; provider?: string; menuSelectionProvider?: string };
const examples = ["우리 3명인데 한 명은 채식, 한 명은 매운 걸 못 먹어", "안 맵고 따뜻한 거 만원 정도로 추천해줘", "땅콩 알레르기 있어. 다른 메뉴는?", "추천한 거 전부 담아줘"];
const welcome = "안녕하세요! 먼저 먹고 가실지, 가져가실지 골라 주세요. 그다음 평소 말하듯 주문하시면 돼요. 🍊";

export function CustomerApp({ slug }: { slug: string }) {
  const [bundle, setBundle] = useState<Bootstrap | null>(null);
  const [visitMode, setVisitMode] = useState<VisitMode | null>(null);
  const [summary, setSummary] = useState<string[]>([]);
  const [profile, setProfile] = useState<PreferenceProfile>(emptyProfile);
  const [cart, setCart] = useState<Cart>({ items: [], total: 0, canOrder: false });
  const [orders, setOrders] = useState<Order[]>([]);
  const [view, setView] = useState<"talk" | "cart" | "orders" | "menu">("talk");
  const [profileOpen, setProfileOpen] = useState(false);
  const [selected, setSelected] = useState<MenuItemData | null>(null);
  const [selectedAssignment, setSelectedAssignment] = useState<string | undefined>();
  const [optionIds, setOptionIds] = useState<string[]>([]);
  const [quantity, setQuantity] = useState(1);
  const [messages, setMessages] = useState<ChatLine[]>([{ role: "assistant", text: welcome }]);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Bootstrap>(`bootstrap?slug=${encodeURIComponent(slug)}`).then(async (data) => {
      // The chat transcript starts anew on page load. Clear its hidden state as well when no cart needs it.
      const fresh = data.visitMode && !data.cart.items.length
        ? await api<{ reset: boolean; dialogue: DialogueState; summary: string[] }>("conversation/reset", "POST") : null;
      const dialogue = fresh?.reset ? fresh.dialogue : data.dialogue;
      setBundle(data); setVisitMode(data.visitMode); setProfile(data.profile); setCart(data.cart);
      if (data.visitMode) {
        setSummary(fresh?.reset ? fresh.summary : [data.visitMode === "dine_in" ? "먹고 가기" : "가져가기", ...(dialogue.peopleCount ? [`${dialogue.peopleCount}명`] : [])]);
        setMessages([{ role: "assistant", text: fresh?.reset
          ? `${data.visitMode === "dine_in" ? "먹고 가기" : "가져가기"}로 새 대화를 시작할게요. 몇 분인지와 취향을 편하게 말씀해 주세요. 저장한 내 취향은 그대로예요.`
          : `다시 오셨군요! 장바구니에 담은 메뉴부터 이어갈게요. 식사 방식과 일행 조건을 확인해 주세요.` }]);
      }
      const saved = localStorage.getItem("poc09_profile");
      if (saved) try {
        const stored = JSON.parse(saved) as PreferenceProfile;
        const next: PreferenceProfile = {
          ...stored,
          allergies: [...new Set([...stored.allergies, ...data.profile.allergies])],
          dietaryRules: [...stored.dietaryRules, ...data.profile.dietaryRules.filter((rule) => !stored.dietaryRules.some((savedRule) => savedRule.type === rule.type && savedRule.mode === rule.mode))],
          maxSpiceLevel: stored.maxSpiceLevel === undefined ? data.profile.maxSpiceLevel : data.profile.maxSpiceLevel === undefined ? stored.maxSpiceLevel : Math.min(stored.maxSpiceLevel, data.profile.maxSpiceLevel),
        };
        const result = await api<{cart: Cart}>("profile", "POST", next);
        setProfile(next); setCart(result.cart);
      } catch { localStorage.removeItem("poc09_profile"); }
    }).catch((cause) => setError(cause.message));
  }, [slug]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [messages, busy]);

  async function chooseMode(mode: VisitMode) {
    setBusy(true); setError("");
    try {
      const result = await api<{ visitMode: VisitMode; reply: string }>("visit", "POST", { mode });
      setVisitMode(result.visitMode); setSummary([mode === "dine_in" ? "먹고 가기" : "가져가기"]);
      setMessages((current) => [...current, { role: "user", text: mode === "dine_in" ? "먹고 갈게요" : "가져갈게요" }, { role: "assistant", text: result.reply }]);
      setView("talk"); setTimeout(() => inputRef.current?.focus(), 100);
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  async function saveProfile(next: PreferenceProfile) {
    setProfile(next); localStorage.setItem("poc09_profile", JSON.stringify(next));
    try { const result = await api<{cart: Cart}>("profile", "POST", next); setCart(result.cart); setSuccess("취향을 저장했어요."); } catch (cause) { setError((cause as Error).message); }
  }
  async function refreshOrders() { try { setOrders(await api<Order[]>("orders")); } catch (cause) { setError((cause as Error).message); } }
  function openItem(item: MenuItemData, assignedTo?: string, suggestedQuantity = 1) {
    setSelected(item); setSelectedAssignment(assignedTo);
    setOptionIds(item.options.flatMap((group) => group.options.filter((option) => option.isAvailable).slice(0, group.minSelect).map((option) => option.id)));
    setQuantity(suggestedQuantity);
  }
  async function add(item: MenuItemData, assignedTo?: string) {
    setBusy(true); setError("");
    try { setCart(await api<Cart>("cart", "POST", { menuItemId: item.id, quantity, selectedOptionIds: optionIds, assignedTo })); setSelected(null); setSuccess(`${item.name}을 담았어요.`); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  async function updateLine(id: string, count: number) {
    try { setCart(await api<Cart>(`cart/${id}`, count <= 0 ? "DELETE" : "PATCH", count <= 0 ? undefined : { quantity: count })); }
    catch (cause) { setError((cause as Error).message); }
  }
  async function checkout(method: "mock_card" | "mock_cash") {
    if (!cart.canOrder || busy) return;
    setBusy(true); setError("");
    try {
      const order = await api<Order>("checkout", "POST", { idempotencyKey: crypto.randomUUID(), paymentMethod: method, note });
      setCart({ items: [], total: 0, canOrder: false }); setNote(""); setSuccess(`주문 ${order.code} 접수 완료!`);
      setMessages((current) => [...current, { role: "assistant", text: `주문 ${order.code} 접수됐어요! ${order.fulfillmentType === "takeout" ? "가져가기" : "먹고 가기"}로 준비할게요. 🍊` }]);
      await refreshOrders(); setView("orders");
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  async function send(value = draft) {
    const message = value.trim(); if (!message || busy || !visitMode) return;
    setDraft(""); setView("talk"); setMessages((current) => [...current, { role: "user", text: message }]); setBusy(true); setError("");
    try {
      const result = await api<{ reply: string; recommendations?: Recommendation[]; cart?: Cart; dialogue?: DialogueState; summary?: string[]; profile?: PreferenceProfile; nextAction?: string; provider?: string; menuSelectionProvider?: string }>("conversation", "POST", { message });
      setMessages((current) => [...current, { role: "assistant", text: result.reply, recommendations: result.recommendations, confirmCheckout: result.nextAction === "confirm_checkout", provider: result.provider, menuSelectionProvider: result.menuSelectionProvider }]);
      if (result.cart) setCart(result.cart); if (result.summary) setSummary(result.summary);
      if (result.profile) {
        setProfile(result.profile);
        if (localStorage.getItem("poc09_profile")) localStorage.setItem("poc09_profile", JSON.stringify(result.profile));
      }
      if (result.nextAction === "checkout") {
        const order = await api<Order>("checkout", "POST", { idempotencyKey: crypto.randomUUID(), paymentMethod: "mock_card", note });
        setCart({ items: [], total: 0, canOrder: false }); setNote("");
        setMessages((current) => [...current, { role: "assistant", text: `주문 ${order.code} 접수됐어요! ${order.fulfillmentType === "takeout" ? "가져가기" : "먹고 가기"}로 준비할게요. 🍊` }]);
        await refreshOrders(); setView("orders");
      }
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  const count = cart.items.reduce((sum, item) => sum + item.quantity, 0);
  return (
    <div className={`customer-app conversation-app ${profile.largeText ? "large-text" : ""}`}>
      <header className="app-header">
        <Link href="/" className="brand"><span className="brand-mark">ㅁㅁㅈ</span><span>뭐먹지?</span></Link>
        <div className="header-actions"><Link className="header-link" href="/merchant">사장님 화면</Link><button className="icon-button profile-trigger" onClick={() => setProfileOpen(true)} aria-label="내 취향 설정"><Heart size={19}/><span>내 취향</span></button></div>
      </header>
      <main className="talk-shell">
        <div className="talk-hero"><span className="mini-label">TAP · TALK · TOGETHER</span><h1>메뉴판보다, <em>대화부터.</em></h1><p>{bundle?.store.name || "오렌지 테이블"}에서 지금 함께 먹을 음식을 찾아요. 사람 수와 취향을 평소처럼 말해 주세요.</p></div>
        {error && <div className="notice notice-error" role="alert">{error}<button onClick={() => setError("")} aria-label="닫기"><X size={16}/></button></div>}
        {success && <div className="notice notice-success" role="status">{success}<button onClick={() => setSuccess("")} aria-label="닫기"><X size={16}/></button></div>}
        <div className="talk-frame">
          <div className="talk-topbar"><div><MessageCircleMore size={21}/><strong>오늘의 주문 대화</strong></div><span>글 · 스마트폰 음성 키보드</span></div>
          {visitMode && <div className="context-strip" aria-label="대화에서 파악한 조건">{summary.map((entry, index) => <span key={`${entry}-${index}`}>{entry}</span>)}<button onClick={() => setVisitMode(null)}>식사 방식 바꾸기</button></div>}
          <div className="talk-stream" aria-live="polite">
            {messages.map((line, index) => <div key={index} className={`talk-row ${line.role}`}><div className="talk-bubble">{line.text.split("\n").map((part, key) => <span key={key}>{part}<br/></span>)}</div>{(line.provider || line.menuSelectionProvider) && <small className="talk-provider">{line.provider === "groq" ? (line.recommendations?.length ? "AI가 대화를 이해하고 확인된 메뉴에서 골랐어요" : "AI가 대화를 이해했어요") : line.menuSelectionProvider === "openrouter" ? (line.recommendations?.length ? "AI가 확인된 메뉴에서 골랐어요" : "AI가 메뉴를 확인했어요") : line.menuSelectionProvider === "rules" && line.recommendations?.length ? "기본 추천으로 골랐어요" : line.provider === "openrouter" ? "AI가 문장을 이해했어요" : "기본 해석으로 처리했어요"}</small>}
              {line.recommendations?.length ? <div className="talk-recommendations">{line.recommendations.map((rec, recIndex) => <div className="talk-rec" key={`${rec.item.id}-${rec.forMember}-${recIndex}`}><span className="talk-rec-number">{recIndex + 1}</span><span className="talk-rec-emoji">{rec.item.emoji}</span><div><strong>{rec.item.name}</strong><small>{rec.forMember ? `${rec.forMember} · ` : ""}{rec.reason}</small><b>{rec.quantity && rec.quantity > 1 ? `${rec.quantity}${rec.unit || "개"} · 예상 ${money(rec.item.price * rec.quantity)}` : money(rec.item.price)}</b></div><button onClick={() => openItem(rec.item, rec.forMember, rec.quantity)} aria-label={`${rec.item.name} 자세히 보기`}>자세히</button></div>)}{index === messages.length - 1 && <button className="talk-inline-action" onClick={() => send(line.recommendations?.length && line.recommendations.length > 1 ? "추천한 거 전부 담아줘" : "첫 번째 담아줘")}>추천 메뉴 담기 <ArrowRight size={16}/></button>}</div> : null}
              {line.confirmCheckout && <div className="talk-confirm"><button className="button button-primary" onClick={() => send("응")}>네, 모의 결제로 주문해요</button><button className="button button-outline" onClick={() => { setView("cart"); setMessages((current) => [...current, {role:"assistant", text:"장바구니를 다시 확인해 주세요."}]); }}>장바구니 확인</button></div>}
            </div>)}
            {busy && <div className="talk-row assistant"><div className="talk-bubble">잠시만요, 확인하고 있어요…</div></div>}<div ref={endRef}/>
          </div>
          {!visitMode ? <div className="visit-choice"><h2>어떻게 드시나요?</h2><p>방문 상황을 먼저 알려 주세요.</p><div><button onClick={() => chooseMode("dine_in")} disabled={busy}>🍽️ <strong>먹고 가기</strong><small>매장에서 식사해요</small></button><button onClick={() => chooseMode("takeout")} disabled={busy}>🥡 <strong>가져가기</strong><small>포장해서 가져가요</small></button></div></div> : <div className="talk-composer"><div className="talk-examples">{examples.map((example) => <button key={example} disabled={busy} onClick={() => send(example)}>{example}</button>)}</div><form onSubmit={(event) => {event.preventDefault(); send();}}><input ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="예: 세 명인데 한 명은 채식, 뭐 먹을까?" enterKeyHint="send" maxLength={500} aria-label="주문 대화 입력"/><button type="submit" disabled={!draft.trim() || busy} aria-label="메시지 보내기"><Send size={21}/></button></form><small>스마트폰의 음성 키보드로 말해 입력해도 돼요. 앱 자체 음성 인식은 준비 중이에요.</small></div>}
        </div>
        {visitMode && <nav className="talk-utilities" aria-label="주문 보조 기능"><button className={view === "talk" ? "active" : ""} onClick={() => setView("talk")}><MessageCircleMore size={17}/> 대화</button><button className={view === "cart" ? "active" : ""} onClick={() => setView("cart")}><ShoppingBag size={17}/> 장바구니 {count ? <b>{count}</b> : null}</button><button className={view === "orders" ? "active" : ""} onClick={() => {setView("orders"); refreshOrders();}}>주문 내역</button><button className={view === "menu" ? "active" : ""} onClick={() => setView("menu")}>전체 메뉴 참고</button></nav>}
        {view === "cart" && <section className="talk-secondary"><div className="section-heading"><div><span className="mini-label">CART</span><h2>주문 확인</h2></div><button className="button button-outline" onClick={() => {setView("talk"); inputRef.current?.focus();}}>대화로 돌아가기</button></div>{cart.items.length ? <div className="cart-list">{cart.items.map((item) => <article className="cart-line" key={item.id}><span className="cart-emoji">{item.emoji}</span><div className="cart-line-main"><strong>{item.name}</strong>{item.assignedTo && <small>{item.assignedTo}</small>}{item.optionNames.length > 0 && <small>{item.optionNames.join(", ")}</small>}{!item.safety.allowed && <small className="danger-text">조건 확인: {item.safety.reasons.join(", ")}</small>}<b>{money(item.lineTotal)}</b></div><div className="stepper"><button onClick={() => updateLine(item.id, item.quantity - 1)} aria-label="수량 줄이기"><Minus size={15}/></button><span>{item.quantity}</span><button onClick={() => updateLine(item.id, item.quantity + 1)} aria-label="수량 늘리기"><Plus size={15}/></button></div></article>)}</div> : <div className="empty-state">아직 담은 음식이 없어요. 대화에서 “추천해줘”라고 말해 보세요.</div>}<div className="talk-checkout"><div className="total-row"><span>합계</span><strong>{money(cart.total)}</strong></div><label>요청 사항<input value={note} onChange={(event) => setNote(event.target.value)} placeholder="예: 수저 2개 부탁드려요" maxLength={300}/></label><p>내부 테스트용 모의 결제이며 실제 결제는 진행되지 않아요.</p><div><button className="button button-primary" disabled={!cart.canOrder || busy} onClick={() => checkout("mock_card")}>모의 카드 결제로 주문</button><button className="button button-outline" disabled={!cart.canOrder || busy} onClick={() => checkout("mock_cash")}>모의 현장 결제</button></div></div></section>}
        {view === "orders" && <section className="talk-secondary"><div className="section-heading"><div><span className="mini-label">ORDERS</span><h2>내 주문 내역</h2></div><button className="button button-outline" onClick={refreshOrders}>새로고침</button></div>{orders.length ? <div className="order-list">{orders.map((order) => <article className="order-card" key={order.id}><div><span className="order-status">{({placed:"접수 대기",accepted:"접수 완료",preparing:"조리 중",ready:"준비 완료",completed:"완료",cancelled:"취소"} as Record<string,string>)[order.status] || order.status}</span><strong>{order.code}</strong><small>{order.fulfillmentType === "takeout" ? "가져가기" : "먹고 가기"} · {new Date(order.createdAt).toLocaleString("ko-KR")}</small></div><div>{order.lines.map((line) => <p key={line.id}>{line.menuName} × {line.quantity} <b>{money(line.lineTotal)}</b></p>)}</div><strong className="order-total">{money(order.total)}</strong></article>)}</div> : <div className="empty-state">아직 주문 내역이 없어요.</div>}</section>}
        {view === "menu" && <section className="talk-secondary"><div className="section-heading"><div><span className="mini-label">REFERENCE MENU</span><h2>전체 메뉴 참고</h2></div><button className="button button-outline" onClick={() => setView("talk")}>대화로 돌아가기</button></div><p className="fine-print">메뉴판은 참고용이에요. 취향을 말하면 함께 골라드려요.</p><div className="menu-grid">{bundle?.menu.map((item) => <article className={`menu-card ${!item.isAvailable ? "soldout" : ""}`} key={item.id}><button onClick={() => openItem(item)} disabled={!item.isAvailable}><span className="menu-emoji">{item.emoji}</span><span className="menu-card-body"><strong>{item.name}</strong><small>{item.description}</small><span className="menu-card-bottom"><b>{money(item.price)}</b><span className="round-plus"><Plus size={19}/></span></span></span></button>{!item.isAvailable && <span className="soldout-tag">품절</span>}</article>)}</div></section>}
        <div className="talk-footer"><span>ㅁㅁㅈ · Tap · Talk · Together</span><button onClick={() => send("직원 불러줘")} disabled={!visitMode || busy}>직원 부르기</button></div>
      </main>
      {profileOpen && (
        <div className="modal-backdrop" onClick={() => setProfileOpen(false)}>
          <aside
            className="profile-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-head">
              <div>
                <span className="mini-label">MY TASTE</span>
                <h2>내 취향 설정</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setProfileOpen(false)}
                aria-label="닫기"
              >
                <X />
              </button>
            </div>
            <p>
              선택한 조건은 이 주문 세션의 메뉴 추천과 주문 확인에 반영돼요.
            </p>
            <h3>알레르기가 있나요?</h3>
            <p className="fine-print">
              선택한 재료는 사장님이 미포함을 확인한 메뉴만 추천해요.
            </p>
            <div className="choice-grid">
              {ALLERGENS.map(([key, label]) => (
                <button
                  key={key}
                  className={profile.allergies.includes(key) ? "chosen" : ""}
                  onClick={() =>
                    saveProfile({
                      ...profile,
                      allergies: profile.allergies.includes(key)
                        ? profile.allergies.filter((entry) => entry !== key)
                        : [...profile.allergies, key],
                    })
                  }
                >
                  {profile.allergies.includes(key) && <Check size={14} />}{" "}
                  {label}
                </button>
              ))}
            </div>
            <h3>식사 조건</h3>
            <div className="choice-grid">
              {DIET_RULES.map(([key, label]) => (
                <button
                  key={key}
                  className={
                    profile.dietaryRules.some((rule) => rule.type === key)
                      ? "chosen"
                      : ""
                  }
                  onClick={() =>
                    saveProfile({
                      ...profile,
                      dietaryRules: profile.dietaryRules.some(
                        (rule) => rule.type === key,
                      )
                        ? profile.dietaryRules.filter(
                            (rule) => rule.type !== key,
                          )
                        : [
                            ...profile.dietaryRules,
                            { type: key, mode: "strict" },
                          ],
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <h3>선호 예산</h3>
            <label className="budget-field">
              1인 기준 또는 전체 주문 예산 (원)
              <input
                type="number"
                min="0"
                max="1000000"
                value={profile.budget ?? ""}
                onChange={(event) =>
                  saveProfile({
                    ...profile,
                    budget: event.target.value
                      ? Number(event.target.value)
                      : undefined,
                  })
                }
                placeholder="예: 15000"
              />
            </label>
            <h3>맵기 취향</h3>
            <div className="spice-row">
              {[0, 1, 2, 3, 4].map((value) => (
                <button
                  key={value}
                  className={profile.spicePreference === value ? "chosen" : ""}
                  onClick={() =>
                    saveProfile({ ...profile, spicePreference: value })
                  }
                >
                  {value}
                </button>
              ))}
            </div>
            <label className="switch-line">
              <input
                type="checkbox"
                checked={profile.maxSpiceLevel === 0}
                onChange={(event) =>
                  saveProfile({
                    ...profile,
                    maxSpiceLevel: event.target.checked ? 0 : undefined,
                  })
                }
              />
              매운 음식은 절대 제외
            </label>
            <label className="switch-line">
              <input
                type="checkbox"
                checked={!!profile.largeText}
                onChange={(event) =>
                  saveProfile({ ...profile, largeText: event.target.checked })
                }
              />
              글씨 크게 보기
            </label>
            <button
              className="button button-outline full"
              onClick={() => {
                saveProfile(emptyProfile);
                localStorage.removeItem("poc09_profile");
              }}
            >
              설정 초기화
            </button>
            <button
              className="button button-primary full"
              onClick={() => setProfileOpen(false)}
            >
              설정 완료 <Check size={17} />
            </button>
          </aside>
        </div>
      )}
      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div
            className="item-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              onClick={() => setSelected(null)}
              aria-label="닫기"
            >
              <X />
            </button>
            <span className="item-hero-emoji">{selected.emoji}</span>
            <h2>{selected.name}</h2>
            <p>{selected.description}</p>
            <strong className="item-price">{money(selected.price)}</strong>
            <div className="item-facts">
              <span>맵기 {selected.spiceLevel}/4</span>
              <span>
                재료: {selected.ingredients.join(", ") || "점주 확인 필요"}
              </span>
            </div>
            {selected.allergens.filter((entry) => entry.relation === "contains")
              .length > 0 && (
              <div className="allergen-note">
                포함 재료:{" "}
                {selected.allergens
                  .filter((entry) => entry.relation === "contains")
                  .map(
                    (entry) =>
                      ALLERGENS.find(
                        ([key]) => key === entry.allergenKey,
                      )?.[1] || entry.allergenKey,
                  )
                  .join(", ")}
              </div>
            )}
            {profile.allergies.length > 0 && (
              <div className="allergen-note">
                선택한 알레르기 기준:{" "}
                {profile.allergies
                  .map((key) => {
                    const record = selected.allergens.find(
                      (entry) => entry.allergenKey === key,
                    );
                    return `${ALLERGENS.find(([value]) => value === key)?.[1]} ${record?.relation === "excludes" && record.verificationStatus === "merchant_verified" ? "점주 확인 미포함" : "확인 필요/포함"}`;
                  })
                  .join(" · ")}
              </div>
            )}
            {selected.options.map((group) => (
              <div className="option-group" key={group.id}>
                <strong>
                  {group.name}{" "}
                  <small>{group.minSelect ? "필수" : "선택"}</small>
                </strong>
                {group.options.map((option) => (
                  <label key={option.id}>
                    <input
                      type={group.maxSelect === 1 ? "radio" : "checkbox"}
                      name={group.id}
                      checked={optionIds.includes(option.id)}
                      disabled={!option.isAvailable}
                      onChange={() =>
                        setOptionIds(
                          group.maxSelect === 1
                            ? [
                                ...optionIds.filter(
                                  (id) =>
                                    !group.options.some(
                                      (entry) => entry.id === id,
                                    ),
                                ),
                                option.id,
                              ]
                            : optionIds.includes(option.id)
                              ? optionIds.filter((id) => id !== option.id)
                              : [...optionIds, option.id],
                        )
                      }
                    />
                    {option.name}
                    <span>+{money(option.priceDelta)}</span>
                  </label>
                ))}
              </div>
            ))}
            <div className="item-modal-footer">
              <div className="stepper">
                <button
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  aria-label="수량 줄이기"
                >
                  <Minus size={16} />
                </button>
                <span>{quantity}</span>
                <button
                  onClick={() => setQuantity(Math.min(30, quantity + 1))}
                  aria-label="수량 늘리기"
                >
                  <Plus size={16} />
                </button>
              </div>
              <button
                className="button button-primary"
                disabled={busy || !selected.isAvailable}
                onClick={() => add(selected, selectedAssignment)}
              >
                장바구니 담기 <ArrowRight size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
