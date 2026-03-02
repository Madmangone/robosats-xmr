import React from 'react';
import { TextField, Typography, Box } from '@mui/material';

const MoneroPayoutForm = ({ value, onChange, error }) => {
  return (
    <Box>
      <Typography variant="body2" gutterBottom>
        Enter your Monero address to receive payment:
      </Typography>
      <TextField
        fullWidth
        variant="outlined"
        size="small"
        placeholder="XMR address (starts with 4 or 8)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        error={!!error}
        helperText={error}
        sx={{ mt: 1 }}
      />
    </Box>
  );
};

export default MoneroPayoutForm;
