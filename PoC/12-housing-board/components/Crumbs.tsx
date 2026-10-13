/* 빵부스러기: 파생 상세에서 위로 한 번에 올라온다. 마지막 항목이 지금 화면. (shadcn Breadcrumb) */
import Link from 'next/link';
import { Fragment } from 'react';
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from './ui/breadcrumb';

export type Crumb = { label: string; href?: string };

export default function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <Breadcrumb aria-label="현재 위치">
      <BreadcrumbList>
        {items.map((c, i) => (
          <Fragment key={i}>
            {i > 0 ? <BreadcrumbSeparator /> : null}
            <BreadcrumbItem>{c.href ? <BreadcrumbLink render={<Link href={c.href} />}>{c.label}</BreadcrumbLink> : <BreadcrumbPage>{c.label}</BreadcrumbPage>}</BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
