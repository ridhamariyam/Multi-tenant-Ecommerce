import { redirect } from 'next/navigation';

/** The old product listing; older links still point here. */
export default function ShopListPage() {
  redirect('/products');
}
