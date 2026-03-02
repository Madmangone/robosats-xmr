import React, { useContext, useEffect, useState, ClipboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Grid,
  Typography,
  TextField,
  Tooltip,
  FormControlLabel,
  Checkbox,
  useTheme,
  Collapse,
  Switch,
  MenuItem,
  Select,
  InputAdornment,
  Button,
  FormControl,
  InputLabel,
  IconButton,
  FormHelperText,
} from '@mui/material';

import { type Order, type Settings } from '../../../models';
import { decode } from 'light-bolt11-decoder';
import WalletsButton from '../WalletsButton';
import { LoadingButton } from '@mui/lab';
import { pn } from '../../../utils';

import { ContentCopy, Help, SelfImprovement } from '@mui/icons-material';
import { apiClient } from '../../../services/api';

import { systemClient } from '../../../services/System';

import lnproxies from '../../../../static/lnproxies.json';
import { type UseAppStoreType, AppContext } from '../../../contexts/AppContext';

let filteredProxies: Array<Record<string, object>> = [];

const moneroPrefix: string = 'monero:';

export interface MoneroForm {
  invoice: string;
  amount: number;
  advancedOptions: boolean;
  useCustomBudget: boolean;
  routingBudgetUnit: 'PPM' | 'XMR';
  routingBudgetPPM: number;
  routingBudgetXMR: number | undefined;
  badInvoice: string;
  useLnproxy: boolean;
  lnproxyInvoice: string;
  lnproxyAmount: number;
  lnproxyServer: number;
  lnproxyBudgetUnit: 'PPM' | 'XMR';
  lnproxyBudgetPPM: number;
  lnproxyBudgetXMR: number;
  badLnproxy: string;
}

export const defaultMonero: MoneroForm = {
  invoice: '',
  amount: 0,
  advancedOptions: false,
  useCustomBudget: false,
  routingBudgetUnit: 'PPM',
  routingBudgetPPM: 1000,
  routingBudgetXMR: undefined,
  badInvoice: '',
  useLnproxy: false,
  lnproxyInvoice: '',
  lnproxyAmount: 0,
  lnproxyServer: 0,
  lnproxyBudgetUnit: 'XMR',
  lnproxyBudgetPPM: 0,
  lnproxyBudgetXMR: 0,
  badLnproxy: '',
};

interface MoneroPayoutFormProps {
  order: Order;
  loading: boolean;
  monero: MoneroForm;
  setMonero: (state: MoneroForm) => void;
  onClickSubmit: (invoice: string) => void;
  settings: Settings;
}

export const MoneroPayoutForm = ({
  order,
  loading,
  onClickSubmit,
  monero,
  setMonero,
  settings,
}: MoneroPayoutFormProps): React.JSX.Element => {
  const { client } = useContext<UseAppStoreType>(AppContext);
  const { t } = useTranslation();
  const theme = useTheme();

  const [loadingLnproxy, setLoadingLnproxy] = useState<boolean>(false);
  const [noMatchingLnProxies, setNoMatchingLnProxies] = useState<string>('');

  const computeInvoiceAmount = (): number => {
    const tradeAmount = order.trade_piconeros;
    return Math.floor(tradeAmount - tradeAmount * (monero.routingBudgetPPM / 1000000));
  };

  const validateInvoice = (invoice: string, targetAmount: number): string => {
    try {
      const decoded = decode(invoice);
      const invoiceAmount = Math.floor(decoded.sections[2].value / 1000);
      if (targetAmount !== invoiceAmount) {
        return 'Invalid invoice amount';
      } else {
        return '';
      }
    } catch (err) {
      const error = err.toString();
      return `${String(error).substring(0, 100)}${error.length > 100 ? '...' : ''}`;
    }
  };

  useEffect(() => {
    const amount = computeInvoiceAmount();
    setMonero({
      ...monero,
      amount,
      lnproxyAmount: amount - monero.lnproxyBudgetXMR,
      routingBudgetXMR:
        monero.routingBudgetXMR === undefined
          ? Math.ceil((amount / 1000000) * monero.routingBudgetPPM)
          : monero.routingBudgetXMR,
    });
  }, [monero.routingBudgetPPM]);

  useEffect(() => {
    if (monero.invoice !== '') {
      const invoice = monero.invoice.startsWith(moneroPrefix)
        ? monero.invoice.slice(moneroPrefix.length)
        : monero.invoice;

      setMonero({
        ...monero,
        invoice: invoice,
        badInvoice: validateInvoice(invoice, monero.amount),
      });
    }
  }, [monero.invoice, monero.amount]);

  useEffect(() => {
    if (monero.lnproxyInvoice !== '') {
      const invoice = monero.lnproxyInvoice.startsWith(moneroPrefix)
        ? monero.lnproxyInvoice.slice(moneroPrefix.length)
        : monero.lnproxyInvoice;

      setMonero({
        ...monero,
        lnproxyInvoice: invoice,
        badLnproxy: validateInvoice(invoice, monero.lnproxyAmount),
      });
    }
  }, [monero.lnproxyInvoice, monero.lnproxyAmount]);

  // filter lnproxies when the network settings are updated
  let moneroNetwork: string = 'mainnet';
  let internetNetwork: 'Clearnet' | 'I2P' | 'TOR' = 'Clearnet';

  useEffect(() => {
    moneroNetwork = settings?.network ?? 'mainnet';
    if (settings.host?.includes('.i2p') === true) {
      internetNetwork = 'I2P';
    } else if (settings.host?.includes('.onion') === true || client === 'mobile') {
      internetNetwork = 'TOR';
    }

    filteredProxies = lnproxies
      .filter((node) => node.relayType === internetNetwork)
      .filter((node) => node.network === moneroNetwork);
  }, [settings]);

  // if "use lnproxy" checkbox is enabled, but there are no matching proxies, enter error state
  useEffect(() => {
    setNoMatchingLnProxies('');
    if (filteredProxies.length === 0) {
      setNoMatchingLnProxies(
        t(`No proxies available for {{moneroNetwork}} monero over {{internetNetwork}}`, {
          moneroNetwork: settings?.network ?? 'mainnet',
          internetNetwork: t(internetNetwork),
        }),
      );
    }
  }, [monero.useLnproxy]);

  const fetchLnproxy = function (): void {
    setLoadingLnproxy(true);
    const body: { invoice: string; description: string; routing_msat?: string } = {
      invoice: monero.lnproxyInvoice,
      description: '',
    };
    if (monero.lnproxyBudgetXMR > 0) {
      body.routing_msat = String(monero.lnproxyBudgetXMR * 1000);
    }
    apiClient
      .post(filteredProxies[monero.lnproxyServer].url, '', body)
      .then((data) => {
        if (data.reason !== undefined) {
          setMonero({ ...monero, badLnproxy: data.reason });
        } else if (data.proxy_invoice !== undefined) {
          setMonero({ ...monero, invoice: data.proxy_invoice, badLnproxy: '' });
        } else {
          setMonero({ ...monero, badLnproxy: 'Unknown lnproxy response' });
        }
      })
      .catch(() => {
        setMonero({ ...monero, badLnproxy: 'Lnproxy server uncaught error' });
      })
      .finally(() => {
        setLoadingLnproxy(false);
      });
  };

  const handleAdvancedOptions = function (checked: boolean): void {
    if (checked) {
      setMonero({
        ...monero,
        advancedOptions: true,
      });
    } else {
      setMonero({
        ...defaultMonero,
        invoice: monero.invoice,
        amount: monero.amount,
      });
    }
  };

  const onProxyBudgetChange = function (e: React.ChangeEventHandler<HTMLInputElement>): void {
    if (isFinite(e.target.value) && e.target.value >= 0) {
      let lnproxyBudgetXMR;
      let lnproxyBudgetPPM;

      if (monero.lnproxyBudgetUnit === 'XMR') {
        lnproxyBudgetXMR = Math.floor(e.target.value);
        lnproxyBudgetPPM = Math.round((lnproxyBudgetXMR * 1000000) / monero.amount);
      } else {
        lnproxyBudgetPPM = e.target.value;
        lnproxyBudgetXMR = Math.ceil((monero.amount / 1000000) * lnproxyBudgetPPM);
      }

      if (lnproxyBudgetPPM < 99999) {
        const lnproxyAmount = monero.amount - lnproxyBudgetXMR;
        setMonero({ ...monero, lnproxyBudgetXMR, lnproxyBudgetPPM, lnproxyAmount });
      }
    }
  };

  const onRoutingBudgetChange = function (e: React.ChangeEventHandler<HTMLInputElement>): void {
    const tradeAmount = order.trade_piconeros;
    if (isFinite(e.target.value) && e.target.value >= 0) {
      let routingBudgetXMR;
      let routingBudgetPPM;

      if (monero.routingBudgetUnit === 'XMR') {
        routingBudgetXMR = Math.floor(e.target.value);
        routingBudgetPPM = Math.round((routingBudgetXMR * 1000000) / tradeAmount);
      } else {
        routingBudgetPPM = e.target.value;
        routingBudgetXMR = Math.ceil((monero.amount / 1000000) * routingBudgetPPM);
      }

      if (routingBudgetPPM < 99999) {
        const amount = Math.floor(
          tradeAmount - tradeAmount * (monero.routingBudgetPPM / 1000000),
        );
        setMonero({ ...monero, routingBudgetXMR, routingBudgetPPM, amount });
      }
    }
  };

  const lnProxyBudgetHelper = function (): string {
    let text = '';
    if (monero.lnproxyBudgetXMR < 0) {
      text = 'Must be positive';
    } else if (monero.lnproxyBudgetPPM > 10000) {
      text = 'Too high! (That is more than 1%)';
    }
    return text;
  };

  const routingBudgetHelper = function (): string {
    let text = '';
    if (monero.routingBudgetXMR < 0) {
      text = 'Must be positive';
    } else if (monero.routingBudgetPPM > 10000) {
      text = 'Too high! (That is more than 1%)';
    }
    return text;
  };

  const handlePasteProxy = (e: ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text');
    setMonero({ ...monero, lnproxyInvoice: pastedData ?? '' });

    setTimeout(() => {
      const input = document.getElementById('proxy-textfield') as HTMLInputElement;
      input.setSelectionRange(0, 0);
    }, 0);
  };

  const handlePasteInvoice = (e: ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text');
    setMonero({ ...monero, invoice: pastedData ?? '' });

    setTimeout(() => {
      const input = document.getElementById('invoice-textfield') as HTMLInputElement;
      input.setSelectionRange(0, 0);
    }, 0);
  };

  return (
    <Grid container direction='column' justifyContent='flex-start' alignItems='center' spacing={1}>
      <div style={{ height: '0.3em' }} />
      <Grid
        item
        style={{
          display: 'flex',
          alignItems: 'center',
          height: '1.1em',
        }}
      >
        <Typography color='text.primary'>{t('Advanced options')}</Typography>
        <Switch
          size='small'
          checked={monero.advancedOptions}
          onChange={(e) => {
            handleAdvancedOptions(e.target.checked);
          }}
        />
        <SelfImprovement sx={{ color: 'text.primary' }} />
      </Grid>

      <Grid item>
        <Box
          sx={{
            backgroundColor: 'background.paper',
            border: '1px solid',
            width: '18em',
            borderRadius: '0.3em',
            borderColor: theme.palette.mode === 'dark' ? '#434343' : '#c4c4c4',
            padding: '1em',
          }}
        >
          <Grid
            container
            direction='column'
            justifyContent='flex-start'
            alignItems='center'
            spacing={0.5}
          >
            <Collapse in={monero.advancedOptions}>
              <Grid
                container
                direction='column'
                justifyContent='flex-start'
                alignItems='center'
                spacing={0.5}
                padding={0.5}
              >
                <Grid item>
                  <TextField
                    sx={{ width: '14em' }}
                    disabled={!monero.advancedOptions}
                    error={routingBudgetHelper() !== ''}
                    helperText={routingBudgetHelper()}
                    label={t('Routing Budget')}
                    required={true}
                    value={
                      monero.routingBudgetUnit === 'PPM'
                        ? monero.routingBudgetPPM
                        : monero.routingBudgetXMR
                    }
                    variant='outlined'
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position='end'>
                          <Button
                            variant='text'
                            onClick={() => {
                              setMonero({
                                ...monero,
                                routingBudgetUnit:
                                  monero.routingBudgetUnit === 'PPM' ? 'XMR' : 'PPM',
                              });
                            }}
                          >
                            {monero.routingBudgetUnit}
                          </Button>
                        </InputAdornment>
                      ),
                    }}
                    inputProps={{
                      style: {
                        textAlign: 'center',
                      },
                    }}
                    onChange={onRoutingBudgetChange}
                  />
                </Grid>

                <Grid item>
                  <Tooltip
                    enterTouchDelay={0}
                    leaveTouchDelay={4000}
                    placement='top'
                    title={t(
                      `Wrap this invoice using a Lnproxy server to protect your privacy (hides the receiving wallet).`,
                    )}
                  >
                    <div>
                      <FormControlLabel
                        onChange={(e, checked) => {
                          setMonero({
                            ...monero,
                            useLnproxy: checked,
                            invoice: checked ? '' : monero.invoice,
                          });
                        }}
                        checked={monero.useLnproxy}
                        control={<Checkbox />}
                        label={
                          <Typography color={monero.useLnproxy ? 'primary' : 'text.secondary'}>
                            {t('Use Lnproxy')}
                          </Typography>
                        }
                      />{' '}
                      <IconButton
                        component='a'
                        target='_blank'
                        href='https://www.lnproxy.org/about'
                        rel='noreferrer'
                      >
                        <Help sx={{ width: '0.9em', height: '0.9em', color: 'text.secondary' }} />
                      </IconButton>
                    </div>
                  </Tooltip>
                </Grid>

                <Grid item>
                  <Collapse in={monero.useLnproxy}>
                    <Grid
                      container
                      direction='column'
                      justifyContent='flex-start'
                      alignItems='center'
                      spacing={1}
                    >
                      <Grid item>
                        <FormControl error={noMatchingLnProxies !== ''}>
                          <InputLabel id='select-label'>{t('Server')}</InputLabel>
                          <Select
                            sx={{ width: '14em' }}
                            label={t('Server')}
                            labelId='select-label'
                            value={monero.lnproxyServer}
                            onChange={(e) => {
                              setMonero({ ...monero, lnproxyServer: Number(e.target.value) });
                            }}
                          >
                            {filteredProxies.map((lnproxyServer, index) => (
                              <MenuItem key={index} value={index}>
                                <Typography>{lnproxyServer.name}</Typography>
                              </MenuItem>
                            ))}
                          </Select>
                          {noMatchingLnProxies !== '' ? (
                            <FormHelperText>{t(noMatchingLnProxies)}</FormHelperText>
                          ) : (
                            <></>
                          )}
                        </FormControl>
                      </Grid>

                      <Grid item>
                        <TextField
                          sx={{ width: '14em' }}
                          disabled={!monero.useLnproxy}
                          error={lnProxyBudgetHelper() !== ''}
                          helperText={lnProxyBudgetHelper()}
                          label={t('Proxy Budget')}
                          value={
                            monero.lnproxyBudgetUnit === 'PPM'
                              ? monero.lnproxyBudgetPPM
                              : monero.lnproxyBudgetXMR
                          }
                          variant='outlined'
                          InputProps={{
                            endAdornment: (
                              <InputAdornment position='end'>
                                <Button
                                  variant='text'
                                  onClick={() => {
                                    setMonero({
                                      ...monero,
                                      lnproxyBudgetUnit:
                                        monero.lnproxyBudgetUnit === 'PPM' ? 'XMR' : 'PPM',
                                    });
                                  }}
                                >
                                  {monero.lnproxyBudgetUnit}
                                </Button>
                              </InputAdornment>
                            ),
                          }}
                          inputProps={{
                            style: {
                              textAlign: 'center',
                            },
                          }}
                          onChange={onProxyBudgetChange}
                        />
                      </Grid>
                    </Grid>
                  </Collapse>
                </Grid>
              </Grid>
            </Collapse>

            <Grid item>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Typography align='center' variant='body2'>
                  {t('Submit invoice for {{amountXMR}} XMR', {
                    amountXMR: pn(
                      monero.useLnproxy ? monero.lnproxyAmount : monero.amount,
                    ),
                  })}
                </Typography>
                <Tooltip disableHoverListener enterTouchDelay={0} title={t('Copied!')}>
                  <IconButton
                    sx={{ height: '0.5em' }}
                    onClick={() => {
                      systemClient.copyToClipboard(
                        monero.useLnproxy
                          ? String(monero.lnproxyAmount)
                          : String(monero.amount),
                      );
                    }}
                  >
                    <ContentCopy sx={{ width: '0.8em' }} />
                  </IconButton>
                </Tooltip>
              </div>
            </Grid>

            <Grid item>
              {monero.useLnproxy ? (
                <TextField
                  id='proxy-textfield'
                  fullWidth
                  disabled={!monero.useLnproxy}
                  error={monero.badLnproxy !== ''}
                  helperText={monero.badLnproxy !== '' ? t(monero.badLnproxy) : ''}
                  label={t('Invoice to wrap')}
                  required
                  value={monero.lnproxyInvoice}
                  variant='outlined'
                  maxRows={1}
                  onChange={(e) => {
                    setMonero({ ...monero, lnproxyInvoice: e.target.value ?? '' });
                  }}
                  onPaste={(e) => handlePasteProxy(e)}
                />
              ) : (
                <></>
              )}
              <TextField
                id='invoice-textfield'
                fullWidth
                sx={monero.useLnproxy ? { borderRadius: 0 } : {}}
                disabled={monero.useLnproxy}
                error={monero.badInvoice !== ''}
                helperText={monero.badInvoice !== '' ? t(monero.badInvoice) : ''}
                label={monero.useLnproxy ? t('Wrapped invoice') : t('Payout Monero Invoice')}
                required
                value={monero.invoice}
                variant={monero.useLnproxy ? 'filled' : 'standard'}
                multiline={!monero.useLnproxy}
                maxRows={1}
                onChange={(e) => {
                  setMonero({ ...monero, invoice: e.target.value ?? '' });
                }}
                onPaste={(e) => handlePasteInvoice(e, false)}
              />
            </Grid>

            <Grid item style={{ marginTop: 16 }}>
              {monero.useLnproxy ? (
                <LoadingButton
                  loading={loadingLnproxy}
                  disabled={
                    monero.lnproxyInvoice.length < 20 ||
                    noMatchingLnProxies !== '' ||
                    monero.badLnproxy !== ''
                  }
                  onClick={fetchLnproxy}
                  variant='outlined'
                  color='primary'
                  size='large'
                >
                  {t('Wrap')}
                </LoadingButton>
              ) : (
                <></>
              )}
              <LoadingButton
                loading={loading}
                disabled={monero.invoice.length < 20 || monero.badInvoice !== ''}
                onClick={() => {
                  onClickSubmit(monero.invoice);
                }}
                variant='outlined'
                color='primary'
                size='large'
              >
                {t('Submit')}
              </LoadingButton>
            </Grid>
          </Grid>
        </Box>
      </Grid>

      <Grid item>
        <WalletsButton />
      </Grid>
    </Grid>
  );
};

export default MoneroPayoutForm;
