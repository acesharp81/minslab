import Link from "next/link";
import {
  ArrowRight,
  MessageCircleMore,
  Store,
  Sparkles,
  UtensilsCrossed,
} from "lucide-react";

export default function Home() {
  return (
    <main className="landing">
      <header className="site-header">
        <Link href="/" className="brand">
          <span className="brand-mark">ㅁㅁㅈ</span>
          <span>뭐먹지?</span>
        </Link>
        <Link className="header-link" href="/merchant">
          사장님 화면 <ArrowRight size={17} />
        </Link>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <Sparkles size={16} /> Tap · Talk · Together
          </span>
          <h1>
            오늘 뭐 먹지?
            <br />
            <em>말만 해도</em> 골라드려요.
          </h1>
          <p>
            매장에 온 순간, 먹고 가기 또는 가져가기를 고르세요. 일행 수와 취향을
            대화로 알려주면 함께 고르고 바로 주문할 수 있어요.
          </p>
          <div className="hero-actions">
            <Link
              href="/s/orange-table"
              className="button button-primary button-large"
            >
              대화로 주문 시작하기 <ArrowRight size={20} />
            </Link>
            <Link href="/merchant" className="button button-quiet button-large">
              사장님 관리 화면
            </Link>
          </div>
          <div className="hero-note">
            회원가입 없이 시작 · 내부 테스트용 가상 매장 · 결제는 모의 결제
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-sun">✳</div>
          <div className="art-bowl">
            🍊<span>🍚</span>
          </div>
          <div className="art-card art-card-one">“안 맵고 따뜻한 거!”</div>
          <div className="art-card art-card-two">딱 맞는 메뉴 찾았어요 ✨</div>
        </div>
      </section>
      <section className="steps">
        <div>
          <MessageCircleMore />
          <strong>편하게 말해요</strong>
          <span>“만원쯤, 안 매운 걸로”</span>
        </div>
        <div>
          <UtensilsCrossed />
          <strong>함께 맞춰요</strong>
          <span>일행의 취향과 제약까지 반영</span>
        </div>
        <div>
          <Store />
          <strong>바로 주문해요</strong>
          <span>사장님 화면에 즉시 도착</span>
        </div>
      </section>
      <footer className="landing-footer">
        ㅁㅁㅈ · 누구나, 자기 말로 주문할 수 있게.
      </footer>
    </main>
  );
}
