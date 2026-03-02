import { pn } from './prettyNumbers';

interface computeXMRProps {
  amount: number;
  premium?: number;
  fee: number;
  routingBudget?: number;
  rate?: number;
}
const computeXMR = ({
  amount,
  premium = 0,
  fee,
  routingBudget = 0,
  rate = 1,
}: computeXMRProps): string | undefined => {
  const rateWithPremium = rate + premium / 100;
  let XMR = (amount / rateWithPremium) * 100000000;
  XMR = XMR * (1 - fee) * (1 - routingBudget);
  return pn(Math.round(sats));
};

export default computeXMR;
