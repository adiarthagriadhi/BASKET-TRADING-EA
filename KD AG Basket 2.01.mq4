//+------------------------------------------------------------------+
//|                                             12. KD AG Basket.mq4 |
//|                                    Copyright 2019, Krisna Dinata |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2019, Krisna Dinata & Adiartha Griadhi"
#property link      "https://www.mql5.com"
#property version   "2.01"
#property strict

 int SkorPairA1=0;
 int SkorPairA2=0;
 int SkorPairA3=0;
 int SkorPairB1=0;
 int SkorPairB2=0;
 int SkorPairB3=0;
 
extern double Lots=0.5;
extern ENUM_TIMEFRAMES TimeFrame=0;
extern int TakeProfit = 500;
extern int StopLoss= 500;
extern int Jam=2;
extern int JamClose=7;

string signals;
 
//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
//---
  
//---
   return(INIT_SUCCEEDED);
  }
//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
//---
   
  }
//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
//---
double indexA1, indexA2, indexA3, indexB1, indexB2, indexB3;
double ProfitTot= AccountProfit();
//if(ProfitTot>=100);

if (ProfitTot >= 90)
Alert("TOTAL PROFIT =",ProfitTot);
//
//Alert (totalSkor,", ",SkorPairA1,", ",SkorPairA2,", ",SkorPairA3,", ",SkorPairB1,", ",SkorPairB2,", ",SkorPairB3,", ",ProfitTot);

//if(Jam < Hour()&& Hour() <JamClose) return;
int a = OrdersTotal ();
if (a >=32) return;


if(iClose(A1,PERIOD_M5,0)>= iOpen(A1,PERIOD_M15,0))SkorPairA1=1; 
if(iClose(A2,PERIOD_M5,0)>= iOpen(A2,PERIOD_M15,0))SkorPairA2=1;
if(iClose(A3,PERIOD_M5,0)>= iOpen(A3,PERIOD_M15,0))SkorPairA3=1;
if(iClose(B1,PERIOD_M5,0)>= iOpen(B1,PERIOD_M15,0))SkorPairB1=-1;
if(iClose(B2,PERIOD_M5,0)>= iOpen(B2,PERIOD_M15,0))SkorPairB2=-1;
if(iClose(B3,PERIOD_M5,0)>= iOpen(B3,PERIOD_M15,0))SkorPairB3=-1;

if(iClose(A1,PERIOD_M5,0)<iOpen(A1,PERIOD_M15,0))SkorPairA1=-1;
if(iClose(A2,PERIOD_M5,0)<iOpen(A2,PERIOD_M15,0))SkorPairA2=-1;
if(iClose(A3,PERIOD_M5,0)<iOpen(A3,PERIOD_M15,0))SkorPairA3=-1;
if(iClose(B1,PERIOD_M5,0)<iOpen(B1,PERIOD_M15,0))SkorPairB1=1;
if(iClose(B2,PERIOD_M5,0)<iOpen(B2,PERIOD_M15,0))SkorPairB2=1;
if(iClose(B3,PERIOD_M5,0)<iOpen(B3,PERIOD_M15,0))SkorPairB3=1;

indexA1 = (iClose(A1,PERIOD_M15,0)-iOpen(A1,PERIOD_M15,0))/iClose(A1,PERIOD_M15,0)*100;
indexA2 = (iClose(A2,PERIOD_M15,0)-iOpen(A2,PERIOD_M15,0))/iClose(A2,PERIOD_M15,0)*100;
indexA3 = (iClose(A2,PERIOD_M15,0)-iOpen(A2,PERIOD_M15,0))/iClose(A3,PERIOD_M15,0)*100;
indexB1 = (iClose(B1,PERIOD_M15,0)-iOpen(B1,PERIOD_M15,0))/iClose(B1,PERIOD_M15,0)*100;
indexB2 = (iClose(B2,PERIOD_M15,0)-iOpen(B2,PERIOD_M15,0))/iClose(B2,PERIOD_M15,0)*100;
indexB3 = (iClose(B3,PERIOD_M15,0)-iOpen(B3,PERIOD_M15,0))/iClose(B3,PERIOD_M15,0)*100;

int signal=99;




int totalSkor=SkorPairA1+SkorPairA2+SkorPairA3+SkorPairB1+SkorPairB2+SkorPairB3;

   Comment(
   "\n",A1," :",SkorPairA1,
   "\n","Open M15:", iClose(A1,PERIOD_M5,0),
   "\n","Close Price M5:",iClose(A1,PERIOD_M5,0),
   
   "\n",A2," :",SkorPairA2,
   "\n","Open M15:", iOpen(A2,PERIOD_M15,0),
   "\n","Close Price M5:",iClose(A2,PERIOD_M5,0),
   
   "\n",A3," :",SkorPairA3,
   "\n","Open M15:", iOpen(A3,PERIOD_M15,0),
   "\n","Close Price M5:",iClose(A3,PERIOD_M5,0),
   
   "\n",B1, " :",SkorPairB1,
   "\n","Open M15:",iOpen(B1,PERIOD_M15,0),
   "\n","Close Price M5:",iClose(B1,PERIOD_M5,0),
   
   "\n",B2," :",SkorPairB2,
   "\n","Open M15:", iOpen(B2,PERIOD_M15,0),
   "\n","Close Price M5:",iClose(B2,PERIOD_M5,0),
   
  "\n",B3," :",SkorPairB3,
  "\n","Open M15:", iOpen(B3,PERIOD_M15,0),
  "\n","Close Price M5:",iClose(B3,PERIOD_M5,0),
   
   "\n","TOTAL SKOR :",totalSkor
   );
   

if(SkorPairA1+SkorPairA2+SkorPairA3+SkorPairB1+SkorPairB2+SkorPairB3>=4) signal=0;
if(SkorPairA1+SkorPairA2+SkorPairA3+SkorPairB1+SkorPairB2+SkorPairB3<=-4) signal=1;

if(signal==0)int tiketA1= OrderSend(A1,OP_BUY,Lots,MarketInfo(A1,MODE_ASK),10,MarketInfo(A1,MODE_ASK)-StopLoss*Point,MarketInfo(A1,MODE_ASK)+TakeProfit*Point,"BasketBuy");
if(signal==0)int tiketA2= OrderSend(A2,OP_BUY,Lots,MarketInfo(A2,MODE_ASK),10,MarketInfo(A2,MODE_ASK)-StopLoss*Point,MarketInfo(A2,MODE_ASK)+TakeProfit*Point,"BasketBuy");
if(signal==0)int tiketA3= OrderSend(A3,OP_BUY,Lots,MarketInfo(A3,MODE_ASK),10,MarketInfo(A3,MODE_ASK)-StopLoss*Point,MarketInfo(A3,MODE_ASK)+TakeProfit*Point,"BasketBuy");
if(signal==0)int tiketB1= OrderSend(B1,OP_SELL,Lots,MarketInfo(B1,MODE_BID),10,MarketInfo(B1,MODE_BID)+StopLoss*Point,MarketInfo(B1,MODE_BID)-TakeProfit*Point,"BasketSell");
if(signal==0)int tiketB2= OrderSend(B2,OP_SELL,Lots,MarketInfo(B2,MODE_BID),10,MarketInfo(B2,MODE_BID)+StopLoss*Point,MarketInfo(B2,MODE_BID)-TakeProfit*Point,"BasketSell");
if(signal==0)int tiketB3= OrderSend(B3,OP_SELL,Lots,MarketInfo(B3,MODE_BID),10,MarketInfo(B3,MODE_BID)+StopLoss*Point,MarketInfo(B3,MODE_BID)-TakeProfit*Point,"BasketSell");

if(signal==1)int tiketA1= OrderSend(A1,OP_SELL,Lots,MarketInfo(A1,MODE_BID),10,MarketInfo(A1,MODE_BID)+StopLoss*Point,MarketInfo(A1,MODE_BID)-TakeProfit*Point,"BasketSell");
if(signal==1)int tiketA2= OrderSend(A2,OP_SELL,Lots,MarketInfo(A2,MODE_BID),10,MarketInfo(A2,MODE_BID)+StopLoss*Point,MarketInfo(A2,MODE_BID)-TakeProfit*Point,"BasketSell");
if(signal==1)int tiketA3= OrderSend(A3,OP_SELL,Lots,MarketInfo(A3,MODE_BID),10,MarketInfo(A3,MODE_BID)+StopLoss*Point,MarketInfo(A3,MODE_BID)-TakeProfit*Point,"BasketSell");
if(signal==1)int tiketB1= OrderSend(B1,OP_BUY,Lots,MarketInfo(B1,MODE_ASK),10,MarketInfo(B1,MODE_ASK)-StopLoss*Point,MarketInfo(B1,MODE_ASK)+TakeProfit*Point,"BasketBuy");
if(signal==1)int tiketB2= OrderSend(B2,OP_BUY,Lots,MarketInfo(B2,MODE_ASK),10,MarketInfo(B2,MODE_ASK)-StopLoss*Point,MarketInfo(B2,MODE_ASK)+TakeProfit*Point,"BasketBuy");
if(signal==1)int tiketB3= OrderSend(B3,OP_BUY,Lots,MarketInfo(B3,MODE_ASK),10,MarketInfo(B3,MODE_ASK)-StopLoss*Point,MarketInfo(B3,MODE_ASK)+TakeProfit*Point,"BasketBuy");

//if (signal == 0)Alert("STRIGHT SIGNAL!!",signal);
//if (signal == 1)Alert("REVERSE SIGNAL!!", signal);








  }
//+------------------------------------------------------------------+
 double price1=Close[0];
 
 //kalo */usd positif, masing2 nilainya 1, kalo negatif, minus1.
 // kalau usd/* kebalikan. bandingkan dengan posisi open di d1
 
 string A1= "AUDUSD";
 string A2= "EURUSD";
 string A3= "GBPUSD";
 string B1= "USDCAD";
 string B2= "USDCHF";
 string B3= "USDJPY";
 

 bool  OrderClose( 
   int        ticket,      // ticket 
   double     lots,        // volume 
   double     price,       // close price 
   int        slippage,    // slippage 
   color      arrow_color  // color 
   );

 
 
 
 