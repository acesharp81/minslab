export default function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="m-0 mt-2 flex list-none flex-wrap gap-x-[14px] gap-y-1.5 p-0 text-[14px] text-foreground" aria-label="범례">
      {items.map((i) => <li key={i.label} className="flex items-center gap-1.5"><i className="block size-[11px] rounded-[3px]" style={{ background: i.color }} aria-hidden="true" />{i.label}</li>)}
    </ul>
  );
}

/* 표 안의 색 견본: 표의 행 이름 앞에 같은 차트의 색을 붙여, 표가 바로 아래 차트의 범례 노릇도 하게 한다 */
export const Swatch = ({ color }: { color: string }) => <i className="mr-1.5 inline-block size-[11px] rounded-[3px] align-[-1px]" style={{ background: color }} aria-hidden="true" />;
