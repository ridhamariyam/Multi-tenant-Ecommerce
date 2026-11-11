'use client';

import Image from 'next/image';
import { useState } from 'react';

import { formatDate, formatMoney } from '@/lib/format';
import { paymentMethodLabel } from '@/lib/payments/online';
import type { InvoiceRead, Order } from '@/types/orders';

import styles from './Invoice.module.css';

function safeFilename(value: string): string {
  return value.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, '-').replace(/-+/g, '-');
}

function filenameFromHeader(header: string | null): string | null {
  if (!header) return null;
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = header.match(/filename="?([^";]+)"?/i)?.[1];
  const value = encoded ? decodeURIComponent(encoded) : plain;
  return value ? safeFilename(value) : null;
}

export default function Invoice({ order, invoice }: { order: Order; invoice: InvoiceRead }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const money = (value: string) => formatMoney(value, invoice.currency);
  const payments = order.payments?.length ? order.payments : order.payment ? [order.payment] : [];
  const downloadUrl = `/account/invoices/${encodeURIComponent(order.id)}/pdf`;

  async function downloadPdf() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const response = await fetch(downloadUrl, { credentials: 'same-origin' });
      const contentType = response.headers.get('Content-Type') ?? '';
      if (!response.ok || !contentType.toLowerCase().includes('application/pdf')) {
        const normalizedContentType = contentType.toLowerCase();
        const detail = normalizedContentType.includes('text/plain') || normalizedContentType.includes('application/json')
          ? (await response.text()).slice(0, 400)
          : '';
        throw new Error(detail.trim() || 'The invoice PDF could not be downloaded. Please try again.');
      }

      const blob = await response.blob();
      const filename = filenameFromHeader(response.headers.get('Content-Disposition')) ?? `${safeFilename(invoice.invoice_number)}.pdf`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename.toLowerCase().endsWith('.pdf') ? filename : `${filename}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'The invoice PDF could not be downloaded. Please try again.');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <main className={`${styles.page} ${styles.invoicePage}`}>
      <div className={styles.actions}>
        <button type="button" onClick={downloadPdf} disabled={downloading} className={styles.primaryButton}>
          {downloading ? 'Preparing invoice…' : 'Download PDF'}
        </button>
        <button type="button" onClick={() => window.print()} className={styles.outlineButton}>Print Invoice</button>
      </div>
      {downloadError && <p className={styles.downloadError} role="alert">{downloadError}</p>}

      <article className={styles.sheet}>
        <header className={styles.invoiceHeader}>
          <div className={styles.brand}>
            <Image src="/images/cliq-wordmark.svg" alt="CliQ." width={70} height={30} priority />
            {invoice.seller.name && <p>{invoice.seller.name}</p>}
            {invoice.seller.gstin && <p>GSTIN {invoice.seller.gstin}</p>}
          </div>
          <div className={styles.titleBlock}>
            <p className={styles.eyebrow}>CliQ · TAX INVOICE</p>
            <h1>Invoice</h1>
            <strong>{invoice.invoice_number}</strong>
          </div>
        </header>

        <section className={styles.detailsGrid} aria-label="Invoice details">
          <div className={styles.party}>
            <h2>From</h2>
            <strong>{invoice.seller.name ?? '—'}</strong>
            {invoice.seller.address && <p>{invoice.seller.address}</p>}
            {invoice.seller.state && <p>{invoice.seller.state}{invoice.seller.state_code ? ` · ${invoice.seller.state_code}` : ''}</p>}
            {invoice.seller.gstin && <p>GSTIN {invoice.seller.gstin}</p>}
          </div>
          <div className={styles.party}>
            <h2>Bill to</h2>
            <strong>{invoice.buyer.name ?? '—'}</strong>
            {invoice.buyer.address && <p>{invoice.buyer.address}</p>}
            {invoice.buyer.state && <p>{invoice.buyer.state}{invoice.buyer.state_code ? ` · ${invoice.buyer.state_code}` : ''}</p>}
            {order.contact_email && <p>{order.contact_email}</p>}
          </div>
          <div className={styles.meta}>
            <h2>Invoice information</h2>
            <dl>
              <div><dt>Invoice no.</dt><dd>{invoice.invoice_number}</dd></div>
              <div><dt>Order no.</dt><dd>{invoice.order_number}</dd></div>
              <div><dt>Invoice date</dt><dd>{formatDate(invoice.invoice_date)}</dd></div>
              <div><dt>Order status</dt><dd>{invoice.order_status.replaceAll('_', ' ')}</dd></div>
              {invoice.place_of_supply && <div><dt>Place of supply</dt><dd>{invoice.place_of_supply}</dd></div>}
            </dl>
          </div>
          <div className={styles.meta}>
            <h2>Payment information</h2>
            <dl>
              <div><dt>Method</dt><dd>{paymentMethodLabel(order)}</dd></div>
              <div><dt>Status</dt><dd>{order.payment_status.replaceAll('_', ' ')}</dd></div>
              {payments.map((payment, index) => (
                <div key={payment.id}>
                  <dt>{payments.length > 1 ? `Payment ${index + 1}` : payment.provider.replaceAll('_', ' ')}</dt>
                  <dd>{payment.status.replaceAll('_', ' ')} · {formatMoney(payment.amount, payment.currency)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className={styles.shipping} aria-label="Shipping address">
          <h2>Ship to</h2>
          <p><strong>{order.delivery_address.full_name}</strong> · {order.delivery_address.address_line_1}{order.delivery_address.address_line_2 ? `, ${order.delivery_address.address_line_2}` : ''}, {order.delivery_address.city}, {order.delivery_address.state} {order.delivery_address.postal_code}, {order.delivery_address.country}</p>
          <p>{order.delivery_address.phone}</p>
        </section>

        <section className={styles.itemsSection} aria-label="Invoice items">
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr><th>Item / Variant</th><th>Qty</th><th>Unit price</th><th>Discount</th><th>Taxable</th><th>GST</th><th>Total</th></tr>
              </thead>
              <tbody>
                {invoice.lines.map((line, index) => (
                  <tr key={`${line.sku ?? line.description}-${index}`}>
                    <td className={styles.description}>
                      <strong>{line.description}</strong>
                      {(line.sku || line.hsn_code) && <small>{[line.sku && `SKU ${line.sku}`, line.hsn_code && `HSN ${line.hsn_code}`].filter(Boolean).join(' · ')}</small>}
                    </td>
                    <td>{line.quantity}</td>
                    <td>{money(line.unit_price)}</td>
                    <td>{money(line.discount)}</td>
                    <td>{money(line.taxable_value)}</td>
                    <td className={styles.gstCell}>
                      {invoice.tax_split_known ? (
                        <>{line.gst_rate}%<small>CGST {money(line.cgst_amount)}<br />SGST {money(line.sgst_amount)}<br />IGST {money(line.igst_amount)}</small></>
                      ) : '—'}
                    </td>
                    <td className={styles.amount}>{money(line.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className={styles.bottomGrid}>
          <p className={styles.taxNote}>
            {invoice.tax_split_known ? `GST type: ${invoice.gst_type ?? '—'}` : 'GST component split is not available for this order.'}
          </p>
          <dl className={styles.totals}>
            <div><dt>Subtotal</dt><dd>{money(invoice.totals.subtotal)}</dd></div>
            <div><dt>Discount</dt><dd>−{money(invoice.totals.discount)}</dd></div>
            <div><dt>Shipping</dt><dd>{money(invoice.totals.shipping)}</dd></div>
            {Number(invoice.totals.cod_fee) > 0 && <div><dt>COD fee</dt><dd>{money(invoice.totals.cod_fee)}</dd></div>}
            <div><dt>Taxable value</dt><dd>{money(invoice.totals.taxable_value)}</dd></div>
            {invoice.tax_split_known && <>
              <div><dt>CGST</dt><dd>{money(invoice.totals.cgst_amount)}</dd></div>
              <div><dt>SGST</dt><dd>{money(invoice.totals.sgst_amount)}</dd></div>
              <div><dt>IGST</dt><dd>{money(invoice.totals.igst_amount)}</dd></div>
            </>}
            <div><dt>Total tax</dt><dd>{money(invoice.totals.tax_amount)}</dd></div>
            <div className={styles.grandTotal}><dt>Invoice total</dt><dd>{money(invoice.totals.total)}</dd></div>
          </dl>
        </section>

        <footer className={styles.invoiceFooter}>
          <span>Thank you for shopping with CliQ.</span>
          <span>{invoice.invoice_number}</span>
        </footer>
      </article>
    </main>
  );
}
