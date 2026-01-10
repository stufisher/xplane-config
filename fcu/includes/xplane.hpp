#include "esphome.h"
using namespace esphome;

#pragma pack(push, 1)
typedef struct rref_request_type
{
  char cmd[5];
  uint32_t freq;
  uint32_t idx;
  char str[400];
} rref_request_type;
#pragma pack(pop)

typedef struct rref_data_type
{
  uint32_t idx;
  float val;
} rref_data_type;

std::vector<uint8_t> subscribe(std::string dref, uint32_t freq, uint32_t index)
{
  rref_request_type req{"RREF", freq, index};
  for (int x = 0; x < sizeof(req.str); x++)
  {
    req.str[x] = 0x0;
  }
  strcpy(req.str, dref.c_str());

  std::vector<std::uint8_t> bytes(sizeof(req));
  std::memcpy(bytes.data(), reinterpret_cast<void *>(&req), sizeof(req));

  ESP_LOGD("DREF", "%s", dref.c_str());
  ESP_LOGD("LENGTH", "%d", bytes.size());
  ESP_LOGD("PACKET", "%s", format_hex_pretty(bytes).c_str());

  return bytes;
}

// void parse(std::vector<uint8_t> data)
// {
//   std::string cmd;
//   for (uint8_t i = 0; i < 5; i++)
//   {
//     cmd += data[i];
//   }

//   ESP_LOGD("PARSE", "%s", format_hex_pretty(data).c_str());
//   ESP_LOGD("CMD", "%s", cmd.c_str());

//   if (cmd.find("RREF") == 0)
//   {
//     std::map<std::uint8_t, template_::TemplateSensor *> sensors = {
//         {1, id(spd_mgd)},
//         {2, id(spd)},
//         {3, id(hdg_mgd)},
//         {4, id(hdg)},
//         {5, id(alt_mgd)},
//         {6, id(alt)},
//         {7, id(vs)},
//     };

//     uint8_t num_structs = (data.size() - 5) / sizeof(rref_data_type);
//     rref_data_type *f = reinterpret_cast<rref_data_type *>(&data[5]);
//     for (uint8_t j = 0; j < num_structs; j += 1)
//     {
//       auto sensor = sensors.find(f[j].idx);
//       float value = f[j].val;
//       if (value != sensor->state)
//       {
//         sensor->publish_state(value);
//       }

//       ESP_LOGI("RECV", "%d %f", f[j].idx, f[j].val);
//     }
//   }
// }
