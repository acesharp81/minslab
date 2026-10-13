import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/* 이 앱의 카드 다섯 가지(옛 dash.css 의 .panel .kpi .cardlink .src 와 board.css 의 .pnl). shadcn 기본(ring·overflow-hidden·간격 변수)은 쓰지 않고
   역할에 맞춘 글자 크기와 여백을 적용한다. 링크 카드는 <Link className={cardVariants({ variant: "link" })}> 로 쓴다 —
   이름(b) 한 줄과 설명(span) 한두 줄만 담는 낮은 카드다(가는 경로는 카드 자체가 링크라 따로 적지 않는다). */
const cardVariants = cva("border border-border bg-card text-card-foreground shadow-[var(--shadow-card)]", {
  variants: {
    variant: {
      panel: "card-soft mt-4 min-w-0 rounded-[14px] px-5 py-5",
      kpi: "card-soft flex flex-col gap-2 rounded-[12px] px-4 py-4",
      link: "card-lift flex flex-col gap-0.5 rounded-[12px] px-4 py-2 no-underline hover:bg-pn2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary [&_b]:text-[17px] [&_b]:leading-[1.35] [&_span]:text-[14px] [&_span]:leading-[1.45] [&_span]:[word-break:keep-all] [&_span]:text-muted-foreground",
      source: "card-soft mt-2.5 rounded-[12px] px-5 py-4",
      board: "card-soft flex min-w-0 flex-col rounded-[14px] px-5 py-5 [&>svg]:flex-none",
    },
  },
  defaultVariants: { variant: "panel" },
})

function Card({ className, variant, render, ...props }: useRender.ComponentProps<"div"> & VariantProps<typeof cardVariants>) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">({ className: cn(cardVariants({ variant }), className) }, props),
    render,
    state: { slot: "card", variant },
  })
}

export { Card, cardVariants }
