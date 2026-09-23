"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  ChefHat,
  ChevronDown,
  Heart,
  MessageCircleMore,
  Minus,
  Plus,
  Send,
  ShoppingBag,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { api, money } from "../lib/client";
import {
  ALLERGENS,
  DIET_RULES,
  emptyProfile,
  type GroupMember,
  type MenuItemData,
  type PreferenceProfile,
  type Recommendation,
} from "../lib/types";

type CartLine = {
  id: string;
  name: string;
  emoji: string;
  quantity: number;
  unitPrice: number;
  lineTotal: number;
  optionNames: string[];
  safety: { allowed: boolean; reasons: string[] };
};
type Cart = { items: CartLine[]; total: number; canOrder: boolean };
type Bootstrap = {
  store: { name: string; description: string };
  categories: { id: string; name: string }[];
  tables: { code: string; label: string }[];
  table: { code: string; label: string } | null;
  menu: MenuItemData[];
  profile: PreferenceProfile;
  cart: Cart;
};
type Order = {
  id: string;
  code: string;
  status: string;
  total: number;
  createdAt: string;
  paymentStatus: string;
  lines: {
    id: string;
    menuName: string;
    quantity: number;
    lineTotal: number;
  }[];
};
type ChatLine = {
  role: "user" | "assistant";
  text: string;
  recommendations?: Recommendation[];
};
const examples = [
  "안 맵고 따뜻한 거 만원 정도로 추천해줘",
  "오늘 가장 인기 있는 메뉴 추천해줘",
  "채식 메뉴로 골라줘",
];

export function CustomerApp({ slug }: { slug: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tableCode = searchParams.get("table");
  const [bundle, setBundle] = useState<Bootstrap | null>(null);
  const [profile, setProfile] = useState<PreferenceProfile>(emptyProfile);
  const [cart, setCart] = useState<Cart>({
    items: [],
    total: 0,
    canOrder: false,
  });
  const [orders, setOrders] = useState<Order[]>([]);
  const [tab, setTab] = useState<"menu" | "chat" | "cart" | "orders">("menu");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [selected, setSelected] = useState<MenuItemData | null>(null);
  const [selectedAssignment, setSelectedAssignment] = useState<
    string | undefined
  >();
  const [optionIds, setOptionIds] = useState<string[]>([]);
  const [quantity, setQuantity] = useState(1);
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [messages, setMessages] = useState<ChatLine[]>([
    {
      role: "assistant",
      text: "안녕하세요! 오늘은 어떤 게 당기세요? 기분이나 예산을 편하게 적어 주세요. 😊",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    api<Bootstrap>(
      `bootstrap?slug=${encodeURIComponent(slug)}${tableCode ? `&table=${encodeURIComponent(tableCode)}` : ""}`,
    )
      .then(async (data) => {
        setBundle(data);
        const saved = localStorage.getItem("poc09_profile");
        if (saved) {
          try {
            const next = JSON.parse(saved) as PreferenceProfile;
            const result = await api<{ cart: Cart }>("profile", "POST", next);
            setProfile(next);
            setCart(result.cart);
            return;
          } catch {
            localStorage.removeItem("poc09_profile");
          }
        }
        setProfile(data.profile);
        setCart(data.cart);
      })
      .catch((cause) => setError(cause.message));
  }, [slug, tableCode]);

  async function saveProfile(next: PreferenceProfile) {
    setProfile(next);
    localStorage.setItem("poc09_profile", JSON.stringify(next));
    try {
      const result = await api<{ cart: Cart }>("profile", "POST", next);
      setCart(result.cart);
      setSuccess("취향을 저장했어요.");
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function refreshOrders() {
    try {
      setOrders(await api<Order[]>("orders"));
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  function openItem(item: MenuItemData, assignedTo?: string) {
    setSelected(item);
    setSelectedAssignment(assignedTo);
    setOptionIds(
      item.options.flatMap((group) =>
        group.minSelect
          ? group.options
              .filter((option) => option.isAvailable)
              .slice(0, group.minSelect)
              .map((option) => option.id)
          : [],
      ),
    );
    setQuantity(1);
  }
  async function add(item: MenuItemData, assignedTo?: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<Cart>("cart", "POST", {
        menuItemId: item.id,
        quantity,
        selectedOptionIds: optionIds,
        assignedTo,
      });
      setCart(result);
      setSelected(null);
      setSuccess(`${item.name}을 담았어요!`);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function updateLine(id: string, quantity: number) {
    try {
      setCart(
        await api<Cart>(
          `cart/${id}`,
          quantity <= 0 ? "DELETE" : "PATCH",
          quantity <= 0 ? undefined : { quantity },
        ),
      );
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function send(value = draft) {
    const message = value.trim();
    if (!message || busy) return;
    setDraft("");
    setTab("chat");
    setMessages((current) => [...current, { role: "user", text: message }]);
    setBusy(true);
    setError("");
    try {
      const result = await api<{
        reply: string;
        recommendations?: Recommendation[];
        cart?: Cart;
      }>("conversation", "POST", { message, members });
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: result.reply,
          recommendations: result.recommendations,
        },
      ]);
      if (result.cart) setCart(result.cart);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function checkout(method: "mock_card" | "mock_cash") {
    if (!cart.canOrder || busy) return;
    setBusy(true);
    setError("");
    try {
      const order = await api<Order>("checkout", "POST", {
        idempotencyKey: crypto.randomUUID(),
        paymentMethod: method,
        note,
      });
      setSuccess(`주문 ${order.code} 접수 완료!`);
      setCart({ items: [], total: 0, canOrder: false });
      setNote("");
      await refreshOrders();
      setTab("orders");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function callStaff() {
    try {
      await api("help", "POST", { note: "손님이 화면에서 직원 호출" });
      setSuccess("사장님께 알렸어요. 잠시만 기다려 주세요.");
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  const filtered =
    bundle?.menu.filter(
      (item) =>
        item.isPublished &&
        (category === "all" || item.categoryId === category) &&
        (!query || `${item.name} ${item.description}`.includes(query)),
    ) || [];
  return (
    <div className={`customer-app ${profile.largeText ? "large-text" : ""}`}>
      <header className="app-header">
        <Link href="/" className="brand">
          <span className="brand-mark">ㅁㅁㅈ</span>
          <span>뭐먹지?</span>
        </Link>
        <div className="header-actions">
          <button
            className="table-chip"
            onClick={() => document.getElementById("table-select")?.focus()}
          >
            {bundle?.table?.label || "테이블 선택"} <ChevronDown size={15} />
          </button>
          <button
            className="icon-button profile-trigger"
            onClick={() => setProfileOpen(true)}
            aria-label="내 취향 설정"
          >
            <Heart size={20} />
            <span>내 취향</span>
          </button>
        </div>
      </header>
      <main className="app-shell">
        <section className="store-banner">
          <div>
            <span className="mini-label">오늘의 맛있는 선택</span>
            <h1>
              {bundle?.store.name || "메뉴를 준비하고 있어요"} <span>🍊</span>
            </h1>
            <p>{bundle?.store.description}</p>
          </div>
          <div className="table-select-wrap">
            <label htmlFor="table-select">어디에서 드시나요?</label>
            <select
              id="table-select"
              value={bundle?.table?.code || ""}
              onChange={(event) => {
                const params = new URLSearchParams(searchParams.toString());
                if (event.target.value) params.set("table", event.target.value);
                else params.delete("table");
                router.push(`/s/${slug}${params.size ? `?${params}` : ""}`);
              }}
            >
              <option value="">테이블 선택 (선택)</option>
              {bundle?.tables.map((table) => (
                <option key={table.code} value={table.code}>
                  {table.label}
                </option>
              ))}
            </select>
          </div>
        </section>
        <div className="quick-bar">
          <button
            onClick={() => {
              setTab("chat");
              document.getElementById("chat-input")?.focus();
            }}
          >
            <MessageCircleMore size={18} /> 말로 메뉴 찾기
          </button>
          <button onClick={() => setProfileOpen(true)}>
            <Heart size={18} /> 내 취향 맞추기
          </button>
          <button onClick={callStaff}>
            <ChefHat size={18} /> 직원 부르기
          </button>
        </div>
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="닫기">
              <X size={16} />
            </button>
          </div>
        )}
        {success && (
          <div className="notice notice-success" role="status">
            {success}
            <button onClick={() => setSuccess("")} aria-label="닫기">
              <X size={16} />
            </button>
          </div>
        )}
        <nav className="tabs" aria-label="주문 메뉴">
          <button
            className={tab === "menu" ? "active" : ""}
            onClick={() => setTab("menu")}
          >
            메뉴 보기
          </button>
          <button
            className={tab === "chat" ? "active" : ""}
            onClick={() => setTab("chat")}
          >
            추천 대화
          </button>
          <button
            className={tab === "cart" ? "active" : ""}
            onClick={() => setTab("cart")}
          >
            장바구니{" "}
            <span>
              {cart.items.reduce((sum, item) => sum + item.quantity, 0)}
            </span>
          </button>
          <button
            className={tab === "orders" ? "active" : ""}
            onClick={() => {
              setTab("orders");
              refreshOrders();
            }}
          >
            주문 내역
          </button>
        </nav>
        {tab === "menu" && (
          <section className="content-section">
            <div className="section-heading">
              <div>
                <span className="mini-label">MENU</span>
                <h2>먹고 싶은 걸 골라보세요</h2>
              </div>
              <input
                className="search-input"
                placeholder="메뉴 이름 검색"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="메뉴 검색"
              />
            </div>
            <div className="category-row">
              <button
                className={category === "all" ? "selected" : ""}
                onClick={() => setCategory("all")}
              >
                전체
              </button>
              {bundle?.categories.map((entry) => (
                <button
                  key={entry.id}
                  className={category === entry.id ? "selected" : ""}
                  onClick={() => setCategory(entry.id)}
                >
                  {entry.name}
                </button>
              ))}
            </div>
            <div className="menu-grid">
              {filtered.map((item) => (
                <article
                  className={`menu-card ${!item.isAvailable ? "soldout" : ""}`}
                  key={item.id}
                >
                  <button
                    onClick={() => openItem(item)}
                    disabled={!item.isAvailable}
                  >
                    <span className="menu-emoji">{item.emoji}</span>
                    <span className="menu-card-body">
                      <strong>{item.name}</strong>
                      <small>{item.description}</small>
                      <span className="menu-card-bottom">
                        <b>{money(item.price)}</b>
                        <span className="round-plus">
                          <Plus size={19} />
                        </span>
                      </span>
                    </span>
                  </button>
                  {!item.isAvailable && (
                    <span className="soldout-tag">품절</span>
                  )}
                </article>
              ))}
            </div>
            {!filtered.length && (
              <div className="empty-state">
                찾는 메뉴가 없어요. 다른 이름으로 검색해 주세요.
              </div>
            )}
          </section>
        )}
        {tab === "chat" && (
          <section className="chat-layout">
            <div className="chat-main">
              <div className="section-heading">
                <div>
                  <span className="mini-label">TALK</span>
                  <h2>편하게 말해 주세요</h2>
                </div>
                <span className="section-badge">
                  <Sparkles size={14} /> 메뉴 데이터로 확인
                </span>
              </div>
              <div className="chat-stream" aria-live="polite">
                {messages.map((line, index) => (
                  <div key={index} className={`chat-row ${line.role}`}>
                    <div className="chat-bubble">
                      {line.text.split("\n").map((part, key) => (
                        <span key={key}>
                          {part}
                          <br />
                        </span>
                      ))}
                    </div>
                    {line.recommendations?.length ? (
                      <div className="recommend-list">
                        {line.recommendations.map((rec) => (
                          <button
                            key={`${index}-${rec.item.id}-${rec.forMember}`}
                            onClick={() => openItem(rec.item, rec.forMember)}
                          >
                            <span>{rec.item.emoji}</span>
                            <span>
                              <strong>{rec.item.name}</strong>
                              <small>
                                {rec.forMember ? `${rec.forMember} · ` : ""}
                                {rec.reason}
                              </small>
                            </span>
                            <b>{money(rec.item.price)}</b>
                            <ArrowRight size={17} />
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
                {busy && (
                  <div className="chat-row assistant">
                    <div className="chat-bubble">메뉴를 살펴보고 있어요…</div>
                  </div>
                )}
              </div>
              <div className="example-row">
                {examples.map((example) => (
                  <button key={example} onClick={() => send(example)}>
                    {example}
                  </button>
                ))}
              </div>
              <form
                className="chat-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  send();
                }}
              >
                <input
                  id="chat-input"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="예: 따뜻하고 안 매운 메뉴 추천해줘"
                  maxLength={500}
                />
                <button
                  type="submit"
                  disabled={!draft.trim() || busy}
                  aria-label="메시지 보내기"
                >
                  <Send size={20} />
                </button>
              </form>
            </div>
            <aside className="group-card">
              <div className="group-title">
                <Users size={21} />
                <div>
                  <strong>함께 주문해요</strong>
                  <small>한 기기에서 여러 사람의 조건을 설정해요</small>
                </div>
              </div>
              {members.map((member, index) => (
                <div className="member-card" key={member.id}>
                  <div className="member-head">
                    <input
                      aria-label={`${index + 1}번 손님 이름`}
                      value={member.label}
                      onChange={(event) =>
                        setMembers(
                          members.map((value) =>
                            value.id === member.id
                              ? { ...value, label: event.target.value }
                              : value,
                          ),
                        )
                      }
                    />
                    <button
                      onClick={() =>
                        setMembers(
                          members.filter((value) => value.id !== member.id),
                        )
                      }
                      aria-label="손님 삭제"
                    >
                      <X size={16} />
                    </button>
                  </div>
                  <select
                    aria-label="맵기 제한"
                    value={member.maxSpiceLevel ?? ""}
                    onChange={(event) =>
                      setMembers(
                        members.map((value) =>
                          value.id === member.id
                            ? {
                                ...value,
                                maxSpiceLevel: event.target.value
                                  ? Number(event.target.value)
                                  : undefined,
                              }
                            : value,
                        ),
                      )
                    }
                  >
                    <option value="">맵기 제한 없음</option>
                    <option value="0">매운 음식 불가</option>
                    <option value="1">순한 맛만</option>
                  </select>
                  <div className="member-allergens">
                    {ALLERGENS.map(([key, label]) => (
                      <label key={key}>
                        <input
                          type="checkbox"
                          checked={member.allergies.includes(key)}
                          onChange={(event) =>
                            setMembers(
                              members.map((value) =>
                                value.id === member.id
                                  ? {
                                      ...value,
                                      allergies: event.target.checked
                                        ? [...value.allergies, key]
                                        : value.allergies.filter(
                                            (entry) => entry !== key,
                                          ),
                                    }
                                  : value,
                              ),
                            )
                          }
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                  <div className="member-diets">
                    {DIET_RULES.map(([key, label]) => (
                      <label key={key}>
                        <input
                          type="checkbox"
                          checked={member.dietaryRules.some(
                            (rule) => rule.type === key,
                          )}
                          onChange={(event) =>
                            setMembers(
                              members.map((value) =>
                                value.id === member.id
                                  ? {
                                      ...value,
                                      dietaryRules: event.target.checked
                                        ? [
                                            ...value.dietaryRules,
                                            { type: key, mode: "strict" },
                                          ]
                                        : value.dietaryRules.filter(
                                            (rule) => rule.type !== key,
                                          ),
                                    }
                                  : value,
                              ),
                            )
                          }
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              <button
                className="button button-outline full"
                onClick={() =>
                  setMembers([
                    ...members,
                    {
                      id: crypto.randomUUID(),
                      label: `${members.length + 1}번 손님`,
                      allergies: [],
                      dietaryRules: [],
                    },
                  ])
                }
              >
                <Plus size={17} /> 손님 추가
              </button>
              <p className="fine-print">
                대화에서 “3명, 4만원 안에서”처럼 말씀해 보세요.
              </p>
            </aside>
          </section>
        )}
        {tab === "cart" && (
          <section className="cart-layout">
            <div>
              <div className="section-heading">
                <div>
                  <span className="mini-label">CART</span>
                  <h2>장바구니</h2>
                </div>
              </div>
              {cart.items.length ? (
                <div className="cart-list">
                  {cart.items.map((item) => (
                    <article className="cart-line" key={item.id}>
                      <span className="cart-emoji">{item.emoji}</span>
                      <div className="cart-line-main">
                        <strong>{item.name}</strong>
                        {item.optionNames.length > 0 && (
                          <small>{item.optionNames.join(", ")}</small>
                        )}
                        {!item.safety.allowed && (
                          <small className="danger-text">
                            조건 재확인: {item.safety.reasons.join(", ")}
                          </small>
                        )}
                        <b>{money(item.lineTotal)}</b>
                      </div>
                      <div className="stepper">
                        <button
                          onClick={() => updateLine(item.id, item.quantity - 1)}
                          aria-label="수량 줄이기"
                        >
                          <Minus size={15} />
                        </button>
                        <span>{item.quantity}</span>
                        <button
                          onClick={() => updateLine(item.id, item.quantity + 1)}
                          aria-label="수량 늘리기"
                        >
                          <Plus size={15} />
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <ShoppingBag size={38} />
                  <strong>아직 담은 메뉴가 없어요</strong>
                  <button
                    className="button button-primary"
                    onClick={() => setTab("menu")}
                  >
                    메뉴 보러 가기 <ArrowRight size={16} />
                  </button>
                </div>
              )}
            </div>
            <aside className="checkout-card">
              <h3>주문 확인</h3>
              <div className="total-row">
                <span>총 결제 금액</span>
                <strong>{money(cart.total)}</strong>
              </div>
              <label>
                요청 사항
                <input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="예: 수저 2개 부탁드려요"
                  maxLength={300}
                />
              </label>
              <p>현재 내부 테스트 중이에요. 실제 결제는 이뤄지지 않아요.</p>
              <button
                className="button button-primary full"
                disabled={!cart.canOrder || busy}
                onClick={() => checkout("mock_card")}
              >
                모의 카드 결제로 주문 <ArrowRight size={18} />
              </button>
              <button
                className="button button-outline full"
                disabled={!cart.canOrder || busy}
                onClick={() => checkout("mock_cash")}
              >
                모의 현장 결제로 주문
              </button>
            </aside>
          </section>
        )}
        {tab === "orders" && (
          <section className="content-section">
            <div className="section-heading">
              <div>
                <span className="mini-label">ORDERS</span>
                <h2>내 주문 내역</h2>
              </div>
              <button className="button button-outline" onClick={refreshOrders}>
                새로고침
              </button>
            </div>
            {orders.length ? (
              <div className="order-list">
                {orders.map((order) => (
                  <article className="order-card" key={order.id}>
                    <div>
                      <span className="order-status">
                        {(
                          {
                            placed: "접수 대기",
                            accepted: "접수 완료",
                            preparing: "조리 중",
                            ready: "준비 완료",
                            completed: "완료",
                            cancelled: "취소",
                          } as Record<string, string>
                        )[order.status] || order.status}
                      </span>
                      <strong>{order.code}</strong>
                      <small>
                        {new Date(order.createdAt).toLocaleString("ko-KR")}
                      </small>
                    </div>
                    <div>
                      {order.lines.map((line) => (
                        <p key={line.id}>
                          {line.menuName} × {line.quantity}{" "}
                          <b>{money(line.lineTotal)}</b>
                        </p>
                      ))}
                    </div>
                    <strong className="order-total">
                      {money(order.total)}
                    </strong>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-state">아직 주문 내역이 없어요.</div>
            )}
          </section>
        )}
      </main>
      <div className="mobile-cart-bar" hidden={tab === "cart"}>
        <button onClick={() => setTab("cart")}>
          <ShoppingBag size={20} /> 장바구니{" "}
          <strong>{money(cart.total)}</strong>
          <ArrowRight size={18} />
        </button>
      </div>
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
